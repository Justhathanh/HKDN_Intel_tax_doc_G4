"""Helper test doc lap parser cua Quoc An."""
import os
import subprocess


def test_an_parser_independent(fixtures_dir, files_gt):
    # Lay code parser tu git cua branch An
    repo_root = os.path.dirname(os.path.dirname(fixtures_dir))
    cmd = ["git", "show", "origin/G4T-61-G4T-46-xml-parsing:backend/app/xml_parser.py"]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print("  Khong the lay parser tu branch cua An:", res.stderr)
        return

    module_dict = {}
    exec(res.stdout, module_dict)
    parse_invoice_xml = module_dict["parse_invoice_xml"]

    xml_dir = os.path.join(fixtures_dir, "xml")
    passed_count = 0
    total_xml = 0

    for fname, meta in sorted(files_gt.items()):
        if not fname.endswith(".xml") or meta.get("schema_passed") is False:
            continue
        total_xml += 1
        with open(os.path.join(xml_dir, fname), "rb") as f:
            data = f.read()
        seller_mst = meta.get("fields", {}).get("seller_tax_id", "0109988776")
        parse_res = parse_invoice_xml(data, seller_mst)
        is_ok = parse_res.schema_check.passed and len(parse_res.schema_check.missing_required) == 0
        if is_ok:
            passed_count += 1
            inv_no = parse_res.field("invoice_number").normalized_value
            gross = parse_res.field("gross_total").normalized_value
            print(f"  * {fname:<36} -> Parse: PASS | So HD: {inv_no} | Tong tien: {gross:>10} VND")
        else:
            print(f"  * {fname:<36} -> Parse: FAIL | Missing: {parse_res.schema_check.missing_required}")

    print(f"  ==> Ket qua Parse XML tren bo du lieu doc lap: {passed_count}/{total_xml} XML PASSED!")
