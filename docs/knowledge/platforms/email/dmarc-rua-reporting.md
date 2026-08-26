# dmarc-rua-reporting

**Issue:** Parsing and acting on DMARC aggregate (RUA) XML reports
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You receive daily `.xml.gz` files from ISPs but cannot interpret what sources are sending as your domain or whether authentication is passing.

## Pattern / Solution
RUA reports arrive as gzipped XML. Sample structure:
```xml
<feedback>
  <report_metadata>
    <org_name>Google Inc.</org_name>
    <date_range><begin>1720742400</begin><end>1720828799</end></date_range>
  </report_metadata>
  <policy_published>
    <domain>yourdomain.com</domain>
    <p>reject</p>
  </policy_published>
  <record>
    <row>
      <source_ip>209.85.220.41</source_ip>
      <count>1423</count>
      <policy_evaluated><disposition>none</disposition><dkim>pass</dkim><spf>pass</spf></policy_evaluated>
    </row>
  </record>
</feedback>
```

Parse in Python:
```python
import gzip, xml.etree.ElementTree as ET
with gzip.open("report.xml.gz") as f:
    tree = ET.parse(f)
root = tree.getroot()
for record in root.findall(".//record"):
    ip = record.findtext(".//source_ip")
    count = record.findtext(".//count")
    dkim = record.findtext(".//dkim")
    spf = record.findtext(".//spf")
    print(ip, count, dkim, spf)
```

Managed tools: Postmark DMARC Digests, Dmarcian, Valimail, Google Postmaster Tools.

## Gotchas
- Reports are sent to `rua=` address; if the address is on a different domain you need an external destination record: `yourdomain.com._report._dmarc.reportdomain.com TXT "v=DMARC1"`
- Timestamps are Unix epoch in UTC
- A single IP with a high `count` and `dkim=fail spf=fail` is a spoofing signal or a misconfigured sender

## Related
- `dmarc-policy-setup.md`
- `dmarc-ruf-forensic.md`
- `google-postmaster-setup.md`
