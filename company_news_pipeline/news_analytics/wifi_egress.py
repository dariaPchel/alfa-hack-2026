"""Fail-closed RouterAI host routing through the active physical Wi-Fi link."""

from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from dataclasses import dataclass


class WifiEgressError(RuntimeError):
    """Raised when Wi-Fi-only routing cannot be confirmed."""


@dataclass(frozen=True)
class WifiInterface:
    alias: str
    index: int
    address: str
    gateway: str


def _powershell(script: str) -> str:
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise WifiEgressError("Windows network route inspection timed out") from exc
    except OSError as exc:
        raise WifiEgressError("Windows PowerShell is unavailable for route inspection") from exc
    if completed.returncode != 0:
        raise WifiEgressError("Windows route inspection failed")
    return completed.stdout.strip()


def _wifi_interface() -> WifiInterface:
    adapter_script = """Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Wi-Fi|Wireless|802.11' } | Select-Object -First 1 InterfaceAlias,InterfaceDescription,ifIndex | ConvertTo-Json -Compress"""
    try:
        adapter = json.loads(_powershell(adapter_script) or "null")
    except (json.JSONDecodeError, TypeError) as exc:
        raise WifiEgressError("Could not parse active Wi-Fi adapter") from exc
    if not isinstance(adapter, dict) or not adapter.get("ifIndex"):
        raise WifiEgressError("No active Wi-Fi interface with an IPv4 gateway was found")
    index = int(adapter["ifIndex"])
    config_script = f"""Get-NetIPConfiguration -InterfaceIndex {index} -ErrorAction Stop | Select-Object InterfaceAlias,InterfaceIndex,@{{N='Address';E={{$_.IPv4Address[0].IPAddress}}}},@{{N='Gateway';E={{$_.IPv4DefaultGateway[0].NextHop}}}} | ConvertTo-Json -Compress"""
    try:
        config = json.loads(_powershell(config_script) or "null")
    except (json.JSONDecodeError, TypeError) as exc:
        raise WifiEgressError("Could not parse Wi-Fi IP configuration") from exc
    if (not isinstance(config, dict) or not config.get("Address") or not config.get("Gateway")
            or int(config.get("InterfaceIndex", -1)) != index):
        raise WifiEgressError("The active Wi-Fi adapter has no IPv4 address and gateway")
    return WifiInterface(str(config["InterfaceAlias"]), index, str(config["Address"]), str(config["Gateway"]))


def ensure_routerai_wifi_routes(host: str = "routerai.ru") -> dict[str, object]:
    """Install/verify narrow /32 routes in ActiveStore; never edits the default route."""

    interface = _wifi_interface()
    try:
        addresses = sorted({str(ipaddress.ip_address(result[4][0])) for result in socket.getaddrinfo(host, 443)
                            if result[0] == socket.AF_INET})
    except OSError as exc:
        raise WifiEgressError("RouterAI host DNS lookup failed") from exc
    if not addresses:
        raise WifiEgressError("RouterAI has no IPv4 address for Wi-Fi-scoped routing")

    for address in addresses:
        prefix = f"{address}/32"
        check = f"$r=Get-NetRoute -DestinationPrefix '{prefix}' -ErrorAction SilentlyContinue | Where-Object {{$_.InterfaceIndex -eq {interface.index}}}; if ($r) {{'present'}} else {{'missing'}}"
        if _powershell(check) != "present":
            add = (f"New-NetRoute -DestinationPrefix '{prefix}' -InterfaceIndex {interface.index} "
                   f"-NextHop '{interface.gateway}' -PolicyStore ActiveStore -ErrorAction Stop | Out-Null; 'added'")
            try:
                _powershell(add)
            except WifiEgressError as exc:
                raise WifiEgressError("Wi-Fi host route could not be installed; RouterAI inference is blocked") from exc
        verify = (f"(Find-NetRoute -RemoteIPAddress '{address}' | Where-Object "
                  "{$_.PSObject.Properties.Name -contains 'InterfaceIndex'} | Select-Object -First 1 -ExpandProperty InterfaceIndex)")
        try:
            selected_interface = int(_powershell(verify))
        except (ValueError, WifiEgressError) as exc:
            raise WifiEgressError("RouterAI route selection could not be verified; inference is blocked") from exc
        if selected_interface != interface.index:
            raise WifiEgressError("Windows selected a non-Wi-Fi route for RouterAI; inference is blocked")
    return {"host": host, "interface_alias": interface.alias, "interface_index": interface.index,
            "source_ipv4": interface.address, "destination_ipv4": addresses, "route_scope": "host /32 in ActiveStore"}
