"""Parser chưa nối vào luồng upload; được giữ để luồng xử lý nền dùng sau."""
import pytest

from app.xml_parser import direction, parse_invoice, UnsafeXml

BUYER, SELLER = "0312345678", "0109876543"
XML = f"""<HDon><DLHDon><TTChung><SHDon>0000123</SHDon></TTChung><NDHDon><NBan><MST>{SELLER}</MST></NBan>
<NMua><MST>{BUYER}</MST></NMua><TToan><TgTCThue>100</TgTCThue></TToan></NDHDon></DLHDon></HDon>""".encode()


def test_fields_with_path_and_missing_is_not_zero():
    f = {x.name: x for x in parse_invoice(XML, BUYER)}
    assert f["invoice_number"].normalized == "0000123" and f["invoice_number"].path.endswith("SHDon")
    assert f["tax_total"].status == "missing" and f["tax_total"].normalized is None
    assert f["direction"].normalized == "incoming"


def test_xxe_blocked():
    with pytest.raises(UnsafeXml):
        parse_invoice(b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>', BUYER)


@pytest.mark.parametrize("seller,buyer,label", [(BUYER, BUYER, "unknown"), (SELLER, "1", "unknown"), (BUYER, SELLER, "outgoing")])
def test_direction(seller, buyer, label):
    assert direction(BUYER, seller, buyer)[0] == label
