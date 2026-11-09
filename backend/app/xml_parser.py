"""Parser XML hoa don co phien ban (EXT 02, EXT 03, EXT 05, EXT 06).

MAPPING_V0 dua tren cau truc XML hoa don dien tu thuong gap va CHUA duoc doi chieu
voi file that. Hai bien the chinh thuc phai duoc chot voi THTax tai G0.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

MAPPING_VERSION = "tt-generic-v0"
MAPPING_V0 = {
    "series_form": "DLHDon/TTChung/KHMSHDon",
    "series": "DLHDon/TTChung/KHHDon",
    "invoice_number": "DLHDon/TTChung/SHDon",
    "issue_date": "DLHDon/TTChung/NLap",
    "currency": "DLHDon/TTChung/DVTTe",
    "seller_name": "DLHDon/NDHDon/NBan/Ten",
    "seller_tax_id": "DLHDon/NDHDon/NBan/MST",
    "buyer_name": "DLHDon/NDHDon/NMua/Ten",
    "buyer_tax_id": "DLHDon/NDHDon/NMua/MST",
    "net_total": "DLHDon/NDHDon/TToan/TgTCThue",
    "tax_total": "DLHDon/NDHDon/TToan/TgTThue",
    "gross_total": "DLHDon/NDHDon/TToan/TgTTTBSo",
}
DECIMAL_FIELDS = {"net_total", "tax_total", "gross_total"}


class UnsafeXml(Exception):
    pass


class MalformedXml(Exception):
    pass


@dataclass
class Field:
    name: str
    raw: str | None
    normalized: str | None
    status: str
    path: str | None


def _find(root, path: str):
    return root.find(".//" + "/".join("{*}" + part for part in path.split("/")))


def _normalize(name: str, raw: str) -> tuple[str | None, str]:
    if name in DECIMAL_FIELDS:
        try:
            return str(Decimal(raw)), "present"
        except InvalidOperation:
            return None, "conflict"
    return raw, "present"


def direction(client_tax_id: str, seller: str | None, buyer: str | None) -> tuple[str, str]:
    """Khach la ben mua: dau vao; ben ban: dau ra; ca hai hoac khong: xung dot (EXT 03)."""
    is_seller, is_buyer = seller == client_tax_id, buyer == client_tax_id
    if is_buyer and not is_seller:
        return "incoming", "present"
    if is_seller and not is_buyer:
        return "outgoing", "present"
    return "unknown", "conflict"


def parse_invoice(data: bytes, client_tax_id: str) -> list[Field]:
    try:
        root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise UnsafeXml(type(exc).__name__) from exc
    except ParseError as exc:
        raise MalformedXml(str(exc)) from exc

    fields: list[Field] = []
    values: dict[str, str | None] = {}
    for name, path in MAPPING_V0.items():
        node = _find(root, path)
        raw = node.text.strip() if node is not None and node.text and node.text.strip() else None
        values[name] = raw
        if raw is None:  # thieu la chua biet, khong phai 0 (EXT 06)
            fields.append(Field(name, None, None, "missing", path))
        else:
            normalized, status = _normalize(name, raw)
            fields.append(Field(name, raw, normalized, status, path))

    label, status = direction(client_tax_id, values["seller_tax_id"], values["buyer_tax_id"])
    fields.append(Field("direction", None, label, status, None))
    return fields
