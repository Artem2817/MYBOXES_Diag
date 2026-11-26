"""Track a USB board across Windows COM number changes."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PortIdentity:
    device: str
    vid: int | None = None
    pid: int | None = None
    serial: str | None = None

def is_slcan(port):
    return 'slcan' in ' '.join(str(getattr(port, key, '') or '') for key in ('description','interface','product')).lower()

def capture_port(device, ports):
    port=next((p for p in ports if p.device==device),None)
    return PortIdentity(device,port.vid,port.pid,port.serial_number) if port else PortIdentity(device)

def find_port(identity, ports):
    if identity is None:return None
    candidates=[p for p in ports if not is_slcan(p)]
    if identity.serial:
        candidates=[p for p in candidates if (p.vid,p.pid,p.serial_number)==(identity.vid,identity.pid,identity.serial)]
    else:
        candidates=[p for p in candidates if p.device==identity.device and (identity.vid is None or (p.vid,p.pid)==(identity.vid,identity.pid))]
    return candidates[0].device if len(candidates)==1 else None
