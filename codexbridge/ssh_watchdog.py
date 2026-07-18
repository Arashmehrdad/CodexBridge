from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig, SSHCommandProfileConfig
from .process_control import process_group_popen_kwargs, terminate_process_tree
from .ssh_commands import (
    build_ssh_argv,
    prepare_ssh_execution,
    resolve_ssh_command_profile,
    resolve_ssh_host,
    validate_ssh_command_profile,
)
from .ssh_tools import run_ssh_environment_probe

_CONTROLLER_LOADER = (
    "exec(__import__('zlib').decompress(__import__('base64').b64decode("
    "''.join(__import__('sys').argv[1:]))))"
)
_CONTROLLER_CHUNK_BYTES = 480


def validate_monitored_command_start(
    config: AppConfig, host_id: str, command_id: str
):
    host, profile = resolve_ssh_command_profile(config, host_id, command_id)
    if not profile.watchdog_eligible:
        raise ValueError("SSH monitored command requires watchdog_eligible=true")
    if not host.watchdog.enabled:
        raise ValueError("SSH monitored command requires an enabled host watchdog")
    return host, profile


def watchdog_termination_active(config: AppConfig, host_id: str, command_id: str) -> bool:
    host, profile = resolve_ssh_command_profile(config, host_id, command_id)
    watchdog = host.watchdog
    return bool(
        watchdog.enabled
        and watchdog.enforcement_mode == "terminate"
        and watchdog.allow_automatic_termination
        and profile.watchdog_eligible
    )


def _encoded_controller_profile(
    command_id: str,
    source: str,
    timeout_seconds: int,
) -> SSHCommandProfileConfig:
    payload = base64.b64encode(zlib.compress(source.encode("utf-8"), level=9)).decode(
        "ascii"
    )
    chunks = [
        payload[index : index + _CONTROLLER_CHUNK_BYTES]
        for index in range(0, len(payload), _CONTROLLER_CHUNK_BYTES)
    ]
    profile = SSHCommandProfileConfig(
        command_id=command_id,
        argv=["python3", "-c", _CONTROLLER_LOADER, *chunks],
        timeout_seconds=timeout_seconds,
    )
    return validate_ssh_command_profile(profile)


def _marker(prefix: str, nonce: str) -> str:
    return f"__CODEXBRIDGE_{prefix}_{nonce}__="


def _extract_marker_payload(line: str, marker: str) -> dict[str, Any] | None:
    marker_index = line.find(marker)
    if marker_index < 0:
        return None
    raw = line[marker_index + len(marker) :].strip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, dict) else None


def _find_marker_payload(text: str, marker: str) -> dict[str, Any] | None:
    for line in reversed(str(text or "").splitlines()):
        payload = _extract_marker_payload(line, marker)
        if payload is not None:
            return payload
    return None


def _valid_remote_identity(payload: dict[str, Any]) -> bool:
    try:
        pid = int(payload.get("pid", 0))
        pgid = int(payload.get("pgid", 0))
        start_time = str(payload.get("start_time_ticks", ""))
    except (TypeError, ValueError):
        return False
    return pid > 1 and pid == pgid and start_time.isdigit() and int(start_time) > 0


def _start_controller_source(
    remote_argv: list[str],
    start_marker: str,
    exit_marker: str,
    controller_state: dict[str, Any],
    *,
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_bytes: bytes = b"",
) -> str:
    encoded_argv = json.dumps(remote_argv, separators=(",", ":"))
    encoded_state = json.dumps(controller_state, sort_keys=True, separators=(",", ":"))
    encoded_working_directory = json.dumps(str(working_directory))
    encoded_environment = json.dumps(environment or {}, sort_keys=True, separators=(",", ":"))
    encoded_stdin = json.dumps(base64.b64encode(stdin_bytes).decode("ascii"))
    return f'''import base64,json,os,subprocess,sys,tempfile,time
argv=json.loads({encoded_argv!r})
contract=json.loads({encoded_state!r})
working_directory=json.loads({encoded_working_directory!r})
environment=json.loads({encoded_environment!r})
stdin_bytes=base64.b64decode(json.loads({encoded_stdin!r}))
remote=contract["remote"]
state_dir=remote["state_dir"]
state_path=remote["state_path"]
input_path=remote["input_path"]
result_path=remote["result_path"]
os.makedirs(state_dir,mode=0o700,exist_ok=True)
def atomic_json(path,payload):
 parent=os.path.dirname(path) or "."
 fd,tmp=tempfile.mkstemp(prefix=".codexbridge-",suffix=".tmp",dir=parent)
 try:
  with os.fdopen(fd,"w",encoding="utf-8",newline="\\n") as handle:
   json.dump(payload,handle,sort_keys=True,separators=(",",":"))
   handle.write("\\n")
   handle.flush()
   os.fsync(handle.fileno())
  os.replace(tmp,path)
  dir_fd=os.open(parent,os.O_RDONLY)
  try:
   os.fsync(dir_fd)
  finally:
   os.close(dir_fd)
 finally:
  try:
   os.unlink(tmp)
  except FileNotFoundError:
   pass
atomic_json(input_path,{{"request_id":contract["request_id"],"execution_id":contract["execution_id"],"idempotency_key":contract["idempotency_key"],"argv":argv,"working_directory":working_directory,"environment":environment,"stdin_size_bytes":len(stdin_bytes),"execution":contract["execution"]}})
child_env=os.environ.copy()
child_env.update(environment)
p=subprocess.Popen(argv,cwd=working_directory or None,env=child_env,stdin=subprocess.PIPE if stdin_bytes else subprocess.DEVNULL,stdout=sys.stdout.buffer,stderr=sys.stderr.buffer,start_new_session=True,close_fds=True)
if stdin_bytes and p.stdin is not None:
 p.stdin.write(stdin_bytes)
 p.stdin.close()
def ident(pid):
 text=open(f"/proc/{{pid}}/stat","r",encoding="utf-8").read()
 rest=text[text.rfind(")")+2:].split()
 return {{"pid":pid,"pgid":int(rest[2]),"start_time_ticks":str(rest[19])}}
try:
 meta=ident(p.pid)
except Exception as exc:
 meta={{"pid":int(p.pid),"pgid":0,"start_time_ticks":"","identity_error":str(exc)[:200]}}
if not (meta.get("pid",0)>1 and meta.get("pid")==meta.get("pgid") and str(meta.get("start_time_ticks","")).isdigit()):
 p.terminate()
 raise RuntimeError("remote process identity could not be verified")
now=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
state=dict(contract)
state["remote"]=dict(remote)
state["remote"].update({{"pid":meta["pid"],"pgid":meta["pgid"],"process_start_identity":meta["start_time_ticks"],"authoritative_state":"running","heartbeat_at":now}})
atomic_json(state_path,state)
start_payload=dict(meta)
start_payload.update({{"execution_id":contract["execution_id"],"state_path":state_path,"authoritative_state":"running","heartbeat_at":now,"durable_ownership":True}})
print({start_marker!r}+json.dumps(start_payload,separators=(",",":")),flush=True)
next_heartbeat=time.monotonic()+5.0
while True:
 rc=p.poll()
 if rc is not None:
  break
 now_mono=time.monotonic()
 if now_mono>=next_heartbeat:
  heartbeat=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
  state["remote"]["heartbeat_at"]=heartbeat
  atomic_json(state_path,state)
  next_heartbeat=now_mono+5.0
 time.sleep(0.2)
ended=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
terminal="completed" if rc==0 else "failed"
result={{"request_id":contract["request_id"],"execution_id":contract["execution_id"],"pid":meta["pid"],"pgid":meta["pgid"],"process_start_identity":meta["start_time_ticks"],"returncode":int(rc),"authoritative_state":terminal,"ended_at":ended}}
atomic_json(result_path,result)
state["remote"].update({{"authoritative_state":terminal,"heartbeat_at":ended,"publication_state":"ready"}})
atomic_json(state_path,state)
print({exit_marker!r}+json.dumps({{"pid":meta.get("pid"),"pgid":meta.get("pgid"),"start_time_ticks":meta.get("start_time_ticks"),"returncode":int(rc),"execution_id":contract["execution_id"],"state_path":state_path,"authoritative_state":terminal}},separators=(",",":")),flush=True)
raise SystemExit(rc)
'''


def _probe_controller_source(
    controller_state: dict[str, Any],
    result_marker: str,
) -> str:
    encoded_state = json.dumps(controller_state, sort_keys=True, separators=(",", ":"))
    return f'''import json,os
contract=json.loads({encoded_state!r})
state_path=contract["remote"]["state_path"]
result_path=contract["remote"]["result_path"]
payload={{"state":None,"result":None,"error":""}}
try:
 with open(state_path,"r",encoding="utf-8") as handle:
  payload["state"]=json.load(handle)
 try:
  with open(result_path,"r",encoding="utf-8") as handle:
   payload["result"]=json.load(handle)
 except FileNotFoundError:
  pass
except FileNotFoundError:
 payload["error"]="state_not_found"
except Exception as exc:
 payload["error"]=str(exc)[:200]
print({result_marker!r}+json.dumps(payload,separators=(",",":")),flush=True)
'''


def probe_remote_controller_state(
    config: AppConfig,
    host_id: str,
    controller_state: dict[str, Any],
) -> dict[str, Any]:
    host = resolve_ssh_host(config, host_id)
    nonce = secrets.token_hex(12)
    result_marker = _marker("REMOTE_STATE", nonce)
    profile = _encoded_controller_profile(
        "monitored_probe",
        _probe_controller_source(controller_state, result_marker),
        30,
    )
    built = build_ssh_argv(config, host_id, profile)
    argv, stdin_text, _ = prepare_ssh_execution(host, built)
    run_kwargs: dict[str, Any] = {
        "cwd": config.config_dir,
        "env": os.environ.copy(),
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "capture_output": True,
        "shell": False,
        "timeout": profile.timeout_seconds,
        "check": False,
    }
    if stdin_text is None:
        run_kwargs["stdin"] = subprocess.DEVNULL
    else:
        run_kwargs["input"] = stdin_text
    try:
        completed = subprocess.run(argv, **run_kwargs)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        payload = _find_marker_payload(stdout, result_marker) or _find_marker_payload(
            stderr, result_marker
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "state": None, "result": None, "error": "probe_timeout"}
    except (OSError, PermissionError) as exc:
        return {"ok": False, "state": None, "result": None, "error": str(exc)[:300]}
    if payload is None:
        return {
            "ok": False,
            "state": None,
            "result": None,
            "error": (stderr.strip() or "remote_state_marker_missing")[:300],
        }
    return {
        "ok": not bool(payload.get("error")),
        "state": payload.get("state") if isinstance(payload.get("state"), dict) else None,
        "result": payload.get("result") if isinstance(payload.get("result"), dict) else None,
        "error": str(payload.get("error", ""))[:300],
    }


def _cancellation_controller_source(
    controller_state: dict[str, Any],
    remote_process: dict[str, Any],
    requested_at: str,
    grace_seconds: int,
    result_marker: str,
) -> str:
    encoded_state = json.dumps(controller_state, sort_keys=True, separators=(",", ":"))
    pid = int(remote_process["pid"])
    pgid = int(remote_process["pgid"])
    start_time = str(remote_process["start_time_ticks"])
    return f'''import json,os,signal,tempfile,time
contract=json.loads({encoded_state!r})
pid={pid}
pgid={pgid}
expected={start_time!r}
requested_at={requested_at!r}
grace={int(grace_seconds)}
state_path=contract["remote"]["state_path"]
result_path=contract["remote"]["result_path"]
result={{"identity_verified":False,"request_persisted":False,"term_sent":False,"kill_sent":False,"terminated":False,"already_exited":False,"identity_changed":False,"completion_persisted":False,"error":""}}
def atomic_json(path,payload):
 parent=os.path.dirname(path) or "."
 fd,tmp=tempfile.mkstemp(prefix=".codexbridge-",suffix=".tmp",dir=parent)
 try:
  with os.fdopen(fd,"w",encoding="utf-8",newline="\\n") as handle:
   json.dump(payload,handle,sort_keys=True,separators=(",",":"))
   handle.write("\\n")
   handle.flush()
   os.fsync(handle.fileno())
  os.replace(tmp,path)
  dir_fd=os.open(parent,os.O_RDONLY)
  try:
   os.fsync(dir_fd)
  finally:
   os.close(dir_fd)
 finally:
  try:
   os.unlink(tmp)
  except FileNotFoundError:
   pass
def read_ident():
 try:
  text=open(f"/proc/{{pid}}/stat","r",encoding="utf-8").read()
 except FileNotFoundError:
  return None
 rest=text[text.rfind(")")+2:].split()
 return {{"pgid":int(rest[2]),"start_time_ticks":str(rest[19])}}
def matches(value):
 return value is not None and value["pgid"]==pgid and value["start_time_ticks"]==expected
def original_gone():
 value=read_ident()
 if value is None:
  return True
 if not matches(value):
  result["identity_changed"]=True
  return True
 return False
try:
 with open(state_path,"r",encoding="utf-8") as handle:
  state=json.load(handle)
except Exception as exc:
 result["error"]="state unavailable: "+str(exc)[:160]
 state=None
if state is not None:
 if state.get("request_id")!=contract.get("request_id") or state.get("execution_id")!=contract.get("execution_id") or state.get("idempotency_key")!=contract.get("idempotency_key") or state.get("controller")!=contract.get("controller"):
  result["error"]="remote controller identity mismatch"
 else:
  remote=state.get("remote") or {{}}
  if int(remote.get("pid") or 0)!=pid or int(remote.get("pgid") or 0)!=pgid or str(remote.get("process_start_identity") or "")!=expected:
   result["error"]="remote persisted process identity mismatch"
  else:
   remote["cancellation_requested_at"]=requested_at
   remote["authoritative_state"]="cancellation_pending"
   remote["heartbeat_at"]=requested_at
   state["remote"]=remote
   atomic_json(state_path,state)
   result["request_persisted"]=True
   current=read_ident()
   if current is None:
    result["terminated"]=True
    result["already_exited"]=True
   elif pid<=1 or pgid<=1 or pid!=pgid or not matches(current):
    result["error"]="remote identity mismatch"
   else:
    result["identity_verified"]=True
    try:
     os.killpg(pgid,signal.SIGTERM)
     result["term_sent"]=True
    except ProcessLookupError:
     result["terminated"]=True
     result["already_exited"]=True
    except Exception as exc:
     result["error"]=str(exc)[:200]
    deadline=time.monotonic()+grace
    while not result["terminated"] and time.monotonic()<deadline:
     if original_gone():
      result["terminated"]=True
      break
     time.sleep(0.1)
    if not result["terminated"] and matches(read_ident()):
     try:
      os.killpg(pgid,signal.SIGKILL)
      result["kill_sent"]=True
     except ProcessLookupError:
      result["terminated"]=True
     except Exception as exc:
      result["error"]=str(exc)[:200]
     deadline=time.monotonic()+2.0
     while not result["terminated"] and time.monotonic()<deadline:
      if original_gone():
       result["terminated"]=True
       break
      time.sleep(0.1)
   if result["terminated"]:
    completed=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    terminal={{"request_id":contract["request_id"],"execution_id":contract["execution_id"],"pid":pid,"pgid":pgid,"process_start_identity":expected,"returncode":-15,"authoritative_state":"cancelled","ended_at":completed,"cancellation_requested_at":requested_at,"cancellation_completed_at":completed}}
    atomic_json(result_path,terminal)
    remote["authoritative_state"]="cancelled"
    remote["heartbeat_at"]=completed
    remote["cancellation_completed_at"]=completed
    remote["publication_state"]="ready"
    state["remote"]=remote
    atomic_json(state_path,state)
    result["completion_persisted"]=True
print({result_marker!r}+json.dumps(result,separators=(",",":")),flush=True)
'''


def cancel_remote_controller(
    config: AppConfig,
    host_id: str,
    controller_state: dict[str, Any],
    remote_process: dict[str, Any],
    *,
    requested_at: str,
    grace_seconds: int,
) -> dict[str, Any]:
    if not _valid_remote_identity(remote_process):
        return {
            "identity_verified": False,
            "request_persisted": False,
            "term_sent": False,
            "kill_sent": False,
            "terminated": False,
            "already_exited": False,
            "identity_changed": False,
            "completion_persisted": False,
            "error": "Remote process identity is incomplete or unsafe",
        }
    host = resolve_ssh_host(config, host_id)
    nonce = secrets.token_hex(12)
    result_marker = _marker("REMOTE_CANCELLATION", nonce)
    profile = _encoded_controller_profile(
        "monitored_cancel",
        _cancellation_controller_source(
            controller_state,
            remote_process,
            requested_at,
            grace_seconds,
            result_marker,
        ),
        max(10, grace_seconds + 8),
    )
    built = build_ssh_argv(config, host_id, profile)
    argv, stdin_text, _ = prepare_ssh_execution(host, built)
    run_kwargs: dict[str, Any] = {
        "cwd": config.config_dir,
        "env": os.environ.copy(),
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "capture_output": True,
        "shell": False,
        "timeout": profile.timeout_seconds,
        "check": False,
    }
    if stdin_text is None:
        run_kwargs["stdin"] = subprocess.DEVNULL
    else:
        run_kwargs["input"] = stdin_text
    try:
        completed = subprocess.run(argv, **run_kwargs)
        payload = _find_marker_payload(completed.stdout or "", result_marker) or _find_marker_payload(completed.stderr or "", result_marker)
        error = completed.stderr or ""
    except subprocess.TimeoutExpired:
        payload = None
        error = "Remote cancellation controller timed out"
    except (OSError, PermissionError) as exc:
        payload = None
        error = str(exc)
    if payload is None:
        return {
            "identity_verified": False,
            "request_persisted": False,
            "term_sent": False,
            "kill_sent": False,
            "terminated": False,
            "already_exited": False,
            "identity_changed": False,
            "completion_persisted": False,
            "error": (error.strip() or "Remote cancellation result marker was not received")[:300],
        }
    return {
        "identity_verified": bool(payload.get("identity_verified")),
        "request_persisted": bool(payload.get("request_persisted")),
        "term_sent": bool(payload.get("term_sent")),
        "kill_sent": bool(payload.get("kill_sent")),
        "terminated": bool(payload.get("terminated")),
        "already_exited": bool(payload.get("already_exited")),
        "identity_changed": bool(payload.get("identity_changed")),
        "completion_persisted": bool(payload.get("completion_persisted")),
        "error": str(payload.get("error", ""))[:300],
    }


def _termination_controller_source(
    remote_process: dict[str, Any],
    grace_seconds: int,
    result_marker: str,
) -> str:
    pid = int(remote_process["pid"])
    pgid = int(remote_process["pgid"])
    start_time = str(remote_process["start_time_ticks"])
    return f'''import json,os,signal,time
pid={pid}
pgid={pgid}
expected={start_time!r}
grace={int(grace_seconds)}
result={{"identity_verified":False,"term_sent":False,"kill_sent":False,"terminated":False,"already_exited":False,"identity_changed":False,"error":""}}
def read_ident():
 try:
  text=open(f"/proc/{{pid}}/stat","r",encoding="utf-8").read()
 except FileNotFoundError:
  return None
 rest=text[text.rfind(")")+2:].split()
 return {{"pgid":int(rest[2]),"start_time_ticks":str(rest[19])}}
def matches(value):
 return value is not None and value["pgid"]==pgid and value["start_time_ticks"]==expected
def original_gone():
 value=read_ident()
 if value is None:
  return True
 if not matches(value):
  result["identity_changed"]=True
  return True
 return False
current=read_ident()
if current is None:
 result["terminated"]=True
 result["already_exited"]=True
elif pid<=1 or pgid<=1 or pid!=pgid or not matches(current):
 result["error"]="remote identity mismatch"
else:
 result["identity_verified"]=True
 try:
  os.killpg(pgid,signal.SIGTERM)
  result["term_sent"]=True
 except ProcessLookupError:
  result["terminated"]=True
  result["already_exited"]=True
 except Exception as exc:
  result["error"]=str(exc)[:200]
 deadline=time.monotonic()+grace
 while not result["terminated"] and time.monotonic()<deadline:
  if original_gone():
   result["terminated"]=True
   break
  time.sleep(0.1)
 if not result["terminated"]:
  current=read_ident()
  if not matches(current):
   result["identity_changed"]=current is not None
   result["terminated"]=True
  else:
   try:
    os.killpg(pgid,signal.SIGKILL)
    result["kill_sent"]=True
   except ProcessLookupError:
    result["terminated"]=True
   except Exception as exc:
    result["error"]=str(exc)[:200]
   deadline=time.monotonic()+2.0
   while not result["terminated"] and time.monotonic()<deadline:
    if original_gone():
     result["terminated"]=True
     break
    time.sleep(0.1)
print({result_marker!r}+json.dumps(result,separators=(",",":")),flush=True)
'''


def terminate_remote_process_group(
    config: AppConfig,
    host_id: str,
    remote_process: dict[str, Any],
    *,
    grace_seconds: int,
) -> dict[str, Any]:
    if not _valid_remote_identity(remote_process):
        return {
            "identity_verified": False,
            "term_sent": False,
            "kill_sent": False,
            "terminated": False,
            "already_exited": False,
            "identity_changed": False,
            "error": "Remote process identity is incomplete or unsafe",
        }
    host = resolve_ssh_host(config, host_id)
    nonce = secrets.token_hex(12)
    result_marker = _marker("REMOTE_TERMINATION", nonce)
    profile = _encoded_controller_profile(
        "monitored_terminate",
        _termination_controller_source(remote_process, grace_seconds, result_marker),
        max(10, grace_seconds + 8),
    )
    built = build_ssh_argv(config, host_id, profile)
    argv, stdin_text, _ = prepare_ssh_execution(host, built)
    run_kwargs: dict[str, Any] = {
        "cwd": config.config_dir,
        "env": os.environ.copy(),
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "capture_output": True,
        "shell": False,
        "timeout": profile.timeout_seconds,
        "check": False,
    }
    if stdin_text is None:
        run_kwargs["stdin"] = subprocess.DEVNULL
    else:
        run_kwargs["input"] = stdin_text
    try:
        completed = subprocess.run(argv, **run_kwargs)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        payload = _find_marker_payload(stdout, result_marker) or _find_marker_payload(
            stderr, result_marker
        )
    except subprocess.TimeoutExpired:
        payload = None
        stderr = "Remote termination controller timed out"
    except (OSError, PermissionError) as exc:
        payload = None
        stderr = str(exc)
    if payload is None:
        return {
            "identity_verified": False,
            "term_sent": False,
            "kill_sent": False,
            "terminated": False,
            "already_exited": False,
            "identity_changed": False,
            "error": (stderr.strip() or "Remote termination result marker was not received")[:300],
        }
    return {
        "identity_verified": bool(payload.get("identity_verified")),
        "term_sent": bool(payload.get("term_sent")),
        "kill_sent": bool(payload.get("kill_sent")),
        "terminated": bool(payload.get("terminated")),
        "already_exited": bool(payload.get("already_exited")),
        "identity_changed": bool(payload.get("identity_changed")),
        "error": str(payload.get("error", ""))[:300],
    }


def _empty_termination() -> dict[str, Any]:
    return {
        "identity_verified": False,
        "term_sent": False,
        "kill_sent": False,
        "terminated": False,
        "already_exited": False,
        "identity_changed": False,
        "error": "",
    }


def _cancelled_before_launch(
    host_id: str,
    command_id: str,
    watchdog_mode: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "cancelled",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "host_id": host_id,
        "ssh_alias": "",
        "command_id": command_id,
        "writes_remote": False,
        "watchdog_mode": watchdog_mode,
        "automatic_termination_active": False,
        "remote_process": {},
        "remote_exit_confirmed": True,
        "watchdog_samples": [],
        "termination": _empty_termination(),
        "safety_failure": False,
        "output_truncated": False,
        "error": "Run was cancelled before the remote command was launched",
        "local_ssh_pid": 0,
    }


def start_monitored_ssh_command(
    config: AppConfig,
    host_id: str,
    command_id: str,
    *,
    run_dir: Path,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    on_event: Callable[[str, str, dict[str, Any]], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
    controller_state: dict[str, Any] | None = None,
    remote_argv: list[str] | None = None,
    working_directory: str = "",
    environment: dict[str, str] | None = None,
    stdin_bytes: bytes = b"",
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    host, profile = validate_monitored_command_start(config, host_id, command_id)
    execution_argv = list(profile.argv) if remote_argv is None else list(remote_argv)
    execution_timeout = profile.timeout_seconds if timeout_seconds is None else timeout_seconds
    if cancellation_check is not None and cancellation_check():
        return _cancelled_before_launch(
            host_id, command_id, host.watchdog.enforcement_mode
        )

    nonce = secrets.token_hex(12)
    start_marker = _marker("REMOTE_START", nonce)
    exit_marker = _marker("REMOTE_EXIT", nonce)
    if controller_state is None:
        raise ValueError("Monitored SSH command requires a remote-controller state contract")
    controller = _encoded_controller_profile(
        "monitored_start",
        _start_controller_source(
            execution_argv,
            start_marker,
            exit_marker,
            controller_state,
            working_directory=working_directory,
            environment=environment,
            stdin_bytes=stdin_bytes,
        ),
        execution_timeout or 604800,
    )
    built = build_ssh_argv(config, host_id, controller)
    argv, stdin_text, destination = prepare_ssh_execution(host, built)
    process = subprocess.Popen(
        argv,
        cwd=config.config_dir,
        env=os.environ.copy(),
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        **process_group_popen_kwargs(),
    )
    if stdin_text is not None and process.stdin is not None:
        process.stdin.write(stdin_text)
        process.stdin.close()
    if process.stdout is None or process.stderr is None:
        terminate_process_tree(process.pid)
        raise RuntimeError("Monitored SSH process did not expose output pipes")

    run_dir.mkdir(parents=True, exist_ok=True)
    state_lock = threading.Lock()
    output_lock = threading.Lock()
    remote_process: dict[str, Any] = {"command_id": command_id, "nonce": nonce}
    remote_exit: dict[str, Any] = {}
    output_parts: dict[str, list[str]] = {"stdout": [], "stderr": []}
    output_totals = {"stdout": 0, "stderr": 0, "captured": 0, "truncated": False}
    last_progress_at = 0.0

    def publish_progress(force: bool = False) -> None:
        nonlocal last_progress_at
        if on_progress is None:
            return
        now = time.monotonic()
        if not force and now - last_progress_at < 1.0:
            return
        last_progress_at = now
        with state_lock:
            identity = {
                "pid": remote_process.get("pid"),
                "pgid": remote_process.get("pgid"),
                "start_time_ticks": remote_process.get("start_time_ticks"),
                "nonce": remote_process.get("nonce"),
                "execution_id": remote_process.get("execution_id"),
                "state_path": remote_process.get("state_path"),
                "authoritative_state": remote_process.get("authoritative_state"),
                "heartbeat_at": remote_process.get("heartbeat_at"),
                "durable_ownership": bool(remote_process.get("durable_ownership")),
            }
        with output_lock:
            output_state = dict(output_totals)
        on_progress(
            {
                "pid": process.pid,
                "remote_process": identity if _valid_remote_identity(identity) else {},
                "ssh_alias": destination,
                "watchdog_mode": host.watchdog.enforcement_mode,
                "automatic_termination_active": watchdog_termination_active(
                    config, host_id, command_id
                ),
                "termination_grace_seconds": host.watchdog.termination_grace_seconds,
                "stdout_bytes": output_state["stdout"],
                "stderr_bytes": output_state["stderr"],
                "captured_output_bytes": output_state["captured"],
                "output_truncated": output_state["truncated"],
                "last_output_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            }
        )

    def pump(pipe, stream_name: str, path: Path) -> None:
        with path.open("w", encoding="utf-8", errors="replace") as handle:
            for line in iter(pipe.readline, ""):
                start_payload = _extract_marker_payload(line, start_marker)
                if start_payload is not None:
                    with state_lock:
                        remote_process.update(start_payload)
                    publish_progress(force=True)
                    continue
                exit_payload = _extract_marker_payload(line, exit_marker)
                if exit_payload is not None:
                    with state_lock:
                        remote_exit.update(exit_payload)
                    publish_progress(force=True)
                    continue
                encoded = line.encode("utf-8", errors="replace")
                with output_lock:
                    output_totals[stream_name] += len(encoded)
                    remaining = max(
                        0, config.ssh.max_output_bytes - output_totals["captured"]
                    )
                    captured = encoded[:remaining]
                    output_totals["captured"] += len(captured)
                    if len(captured) < len(encoded):
                        output_totals["truncated"] = True
                if captured:
                    text = captured.decode("utf-8", errors="replace")
                    handle.write(text)
                    handle.flush()
                    output_parts[stream_name].append(text)
                publish_progress()
        pipe.close()

    stdout_thread = threading.Thread(
        target=pump,
        args=(process.stdout, "stdout", run_dir / "stdout.txt"),
        name=f"ssh-watchdog-stdout-{process.pid}",
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=pump,
        args=(process.stderr, "stderr", run_dir / "stderr.txt"),
        name=f"ssh-watchdog-stderr-{process.pid}",
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    publish_progress(force=True)

    started = time.monotonic()
    last_sample_at = 0.0
    next_termination_attempt_at = 0.0
    breach_streak = 0
    samples: list[dict[str, Any]] = []
    termination = _empty_termination()
    termination_reason = ""
    timed_out = False
    cancellation_requested = False

    while process.poll() is None:
        now = time.monotonic()
        if cancellation_check is not None and cancellation_check():
            cancellation_requested = True
            termination_reason = termination_reason or "cancelled"
        if execution_timeout is not None and not timed_out and now - started >= execution_timeout:
            timed_out = True
            termination_reason = termination_reason or "timed_out"

        with state_lock:
            identity = dict(remote_process)
        identity_ready = _valid_remote_identity(identity)

        if identity_ready and now - last_sample_at >= host.watchdog.poll_interval_seconds:
            last_sample_at = now
            probe = run_ssh_environment_probe(config, host_id)
            sample = {
                "sample_index": len(samples) + 1,
                "status": probe.get("watchdog", {}).get("status", "unknown"),
                "breaches": list(probe.get("watchdog", {}).get("breaches", []))[:10],
            }
            samples.append(sample)
            breached = sample["status"] == "breached"
            breach_streak = breach_streak + 1 if breached else 0
            if on_progress is not None:
                on_progress(
                    {
                        "watchdog_samples": [
                            {
                                "sample_index": item["sample_index"],
                                "status": item["status"],
                                "breach_count": len(item["breaches"]),
                            }
                            for item in samples[-10:]
                        ],
                        "watchdog_breach_streak": breach_streak,
                    }
                )
            if on_event is not None:
                on_event(
                    "warning" if breached else "info",
                    "watchdog",
                    {
                        "sample_index": sample["sample_index"],
                        "status": sample["status"],
                        "breaches": sample["breaches"],
                        "breach_streak": breach_streak,
                    },
                )
            if (
                breached
                and breach_streak >= host.watchdog.consecutive_breaches
                and watchdog_termination_active(config, host_id, command_id)
            ):
                termination_reason = termination_reason or "watchdog"

        if termination_reason and identity_ready and now >= next_termination_attempt_at:
            termination = terminate_remote_process_group(
                config,
                host_id,
                identity,
                grace_seconds=host.watchdog.termination_grace_seconds,
            )
            if on_progress is not None:
                on_progress(
                    {
                        "termination_reason": termination_reason,
                        "termination": termination,
                    }
                )
            if termination["terminated"]:
                deadline = time.monotonic() + host.watchdog.termination_grace_seconds + 2
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.1)
                if process.poll() is None:
                    terminate_process_tree(process.pid)
                break
            next_termination_attempt_at = now + max(
                5, host.watchdog.poll_interval_seconds
            )
        time.sleep(0.1)

    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    local_exit_code = process.poll()
    if local_exit_code is None and termination.get("terminated"):
        terminate_process_tree(process.pid)
        local_exit_code = process.poll()
    if local_exit_code is None:
        local_exit_code = 1

    with state_lock:
        identity = dict(remote_process)
        exit_payload = dict(remote_exit)
    identity_ready = _valid_remote_identity(identity)
    exit_confirmed = bool(
        identity_ready
        and exit_payload
        and int(exit_payload.get("pid", 0)) == int(identity["pid"])
        and int(exit_payload.get("pgid", 0)) == int(identity["pgid"])
        and str(exit_payload.get("start_time_ticks", ""))
        == str(identity["start_time_ticks"])
    )
    if termination.get("terminated"):
        exit_confirmed = True
    child_exit_code = (
        int(exit_payload.get("returncode", local_exit_code))
        if exit_confirmed and exit_payload
        else int(local_exit_code)
    )

    safety_failure = False
    error = ""
    if cancellation_requested:
        if exit_confirmed:
            status = "cancelled"
        else:
            status = "cancellation_pending"
            safety_failure = True
            error = "Cancellation requested but remote process exit is unconfirmed"
    elif timed_out:
        if exit_confirmed:
            status = "timed_out"
        else:
            status = "cancellation_pending"
            safety_failure = True
            error = "Monitored SSH command timed out without confirmed remote termination"
    elif termination_reason == "watchdog":
        if exit_confirmed:
            status = "failed"
            error = "Watchdog threshold triggered confirmed remote termination"
        else:
            status = "cancellation_pending"
            safety_failure = True
            error = "Watchdog termination was requested but remote exit is unconfirmed"
    elif not exit_confirmed:
        status = "cancellation_pending"
        safety_failure = True
        error = "Attached SSH supervisor ended without a verified remote exit marker"
    else:
        status = "completed" if child_exit_code == 0 else "failed"
        if child_exit_code != 0:
            error = f"Remote command exited with code {child_exit_code}"

    with output_lock:
        output_state = dict(output_totals)
    return {
        "ok": status == "completed",
        "status": status,
        "exit_code": child_exit_code,
        "timed_out": timed_out,
        "stdout": "".join(output_parts["stdout"]),
        "stderr": "".join(output_parts["stderr"]),
        "host_id": host_id,
        "ssh_alias": destination,
        "command_id": command_id,
        "writes_remote": bool(profile.writes_remote),
        "watchdog_mode": host.watchdog.enforcement_mode,
        "automatic_termination_active": watchdog_termination_active(
            config, host_id, command_id
        ),
        "remote_process": {
            "pid": identity.get("pid"),
            "pgid": identity.get("pgid"),
            "start_time_ticks": identity.get("start_time_ticks"),
            "nonce": identity.get("nonce"),
            "execution_id": identity.get("execution_id"),
            "state_path": identity.get("state_path"),
            "authoritative_state": identity.get("authoritative_state"),
            "heartbeat_at": identity.get("heartbeat_at"),
            "durable_ownership": bool(identity.get("durable_ownership")),
        }
        if identity_ready
        else {},
        "remote_exit_confirmed": exit_confirmed,
        "watchdog_samples": samples[-10:],
        "termination": termination,
        "termination_reason": termination_reason,
        "safety_failure": safety_failure,
        "output_truncated": bool(output_state["truncated"]),
        "stdout_bytes": int(output_state["stdout"]),
        "stderr_bytes": int(output_state["stderr"]),
        "error": error or str(termination.get("error", "")),
        "local_ssh_pid": process.pid,
    }
