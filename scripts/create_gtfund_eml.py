#!/usr/bin/env python3
"""Creates the 国泰基金 2025年年度电子对账单 .eml fixture file and analyzes its structure."""
import base64
import email
import os
import textwrap
from bs4 import BeautifulSoup

# Complete base64-encoded HTML body from the real 国泰基金 email
# This is the verbatim body content (Content-Transfer-Encoding: base64)
BODY_B64_LINES = [
    "PCFET0NUWVBFIGh0bWwgUFVCTElDICItLy9XM0MvL0RURCBYSFRNTCAxLjAgVHJhbnNpdGlv",
    "bmFsLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL1RSL3hodG1sMS9EVEQveGh0bWwxLXRyYW5z",
    "aXRpb25hbC5kdGQiPgo8aHRtbCB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94aHRt",
    "bCI+CjxoZWFkPgogICAgPG1ldGEgaHR0cC1lcXVpdj0iQ29udGVudC1UeXBlIiBjb250ZW50",
    "PSJ0ZXh0L2h0bWw7IGNoYXJzZXQ9Z2IyMzEyIiAvPgogICAgPHRpdGxlPjwvdGl0bGU+CiAg",
    "ICA8c3R5bGUgdHlwZT0idGV4dC9jc3MiPgo8IS0tCi5TVFlMRTM3IHsJY29sb3I6ICMyMjJh",
    "NjA7Cglmb250LXNpemU6IDE2cHg7Cglmb250LXdlaWdodDogYm9sZDsKCW1hcmdpbjogMDsK",
    "CW1hcmdpbi10b3A6IDVweDsKfQouU1RZTEUzOSB7Y29sb3I6ICNGRjAwMDA7IGZvbnQtc2l6",
    "ZTogMTZweDsgZm9udC13ZWlnaHQ6IGJvbGQ7IG1hcmdpbjogMDsgbWFyZ2luLXRvcDogNXB4",
    "OyB9Ci5TVFlMRTQwIHtjb2xvcjogIzY2NjY2NjsgZm9udC1zaXplOiA5cHg7IGZvbnQtd2Vp",
    "Z2h0OiBib2xkOyBtYXJnaW46IDA7IG1hcmdpbi10b3A6IDVweDsgfQotLT4KICAgIDwvc3R5",
    "bGU+CjwvaGVhZD4K",
]

HEADERS = """\
Received: from mx21.trustsmtp.com (unknown [122.10.32.179])
\tby gzmx12 (Coremail) with SMTP id tSgvCgDXj_ja7WRpO2vzAg--.7334S2;
\tMon, 12 Jan 2026 20:49:30 +0800 (CST)
MIME-Version: 1.0
From: =?utf-8?Q?=E5=9B=BD=E6=B3=B0=E5=9F=BA=E9=87=91?= <service@info.gtfund.com>
To: zsc19921016@163.com
Date: 12 Jan 2026 11:04:54 +0800
Subject: =?utf-8?B?5Zu95rOw5Z+66YeRMjAyNeW5tOW5tOW6pueUteWtkOWvuei0puWNlQ==?=
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: base64

"""

# Since we only have part of the base64, build a representative HTML
# with the ACTUAL column structure from the 国泰基金 annual statement
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title></title></head>
<body>
<table>
  <tr><td>基金账号：</td><td>0212985630/9805351561123</td></tr>
  <tr><td>统计时间段：</td><td>2025-1-1至2025-12-31</td></tr>
  <tr><td>期初总金额：</td><td>58646.89</td></tr>
  <tr><td>期末变化总金额：</td><td>-6076.53</td></tr>
</table>

<h3>投资明细持仓情况</h3>
<table>
  <tr>
    <td>基金代码</td>
    <td>基金名称</td>
    <td>期末净值</td>
    <td>期末持有净值</td>
    <td>状态</td>
  </tr>
  <tr>
    <td>005253</td>
    <td>国泰货币B</td>
    <td>1.000</td>
    <td>8459.91</td>
    <td>继续持有</td>
  </tr>
  <tr>
    <td>017028</td>
    <td>国泰标普500ETF发起联接（QDII）A人民币</td>
    <td>1.5837</td>
    <td>81.48</td>
    <td>继续持有</td>
  </tr>
  <tr>
    <td>160222</td>
    <td>食品</td>
    <td>0.7737</td>
    <td>44028.97</td>
    <td>继续持有</td>
  </tr>
</table>

<h3>基金交易明细记录</h3>
<table>
  <tr>
    <td>申请日期</td>
    <td>确认日期</td>
    <td>基金代码</td>
    <td>基金名称</td>
    <td>业务类型</td>
    <td>确认金额</td>
    <td>基金净值</td>
    <td>手续费</td>
    <td>状态</td>
  </tr>
  <tr>
    <td>2025-01-10</td><td>2025-01-13</td><td>160222</td>
    <td>食品</td><td>基金申购</td><td>3000.00</td><td>0.7899</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-02-18</td><td>2025-02-21</td><td>160222</td>
    <td>食品</td><td>基金申购</td><td>5000.00</td><td>0.7920</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-03-05</td><td>2025-03-08</td><td>160222</td>
    <td>食品</td><td>基金赎回</td><td>2000.00</td><td>0.7850</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-05-20</td><td>2025-05-23</td><td>005253</td>
    <td>国泰货币B</td><td>基金申购</td><td>10000.00</td><td>1.000</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-07-15</td><td>2025-07-16</td><td>005253</td>
    <td>国泰货币B</td><td>基金赎回</td><td>5000.00</td><td>1.000</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-09-10</td><td>2025-09-15</td><td>017028</td>
    <td>国泰标普500ETF发起联接（QDII）A人民币</td><td>基金申购</td><td>500.00</td><td>1.5200</td><td>0.00</td><td>成功</td>
  </tr>
  <tr>
    <td>2025-11-03</td><td>2025-11-06</td><td>160222</td>
    <td>食品</td><td>基金赎回</td><td>1500.00</td><td>0.7700</td><td>0.00</td><td>成功</td>
  </tr>
</table>
</body>
</html>
"""

def create_eml():
    html_bytes = HTML_TEMPLATE.encode('utf-8')
    b64_body = base64.encodebytes(html_bytes).decode('ascii')
    
    eml_path = os.path.join(
        os.path.dirname(__file__), 
        '../tests/fixtures/emails/2025_gtfund_annual_statement.eml'
    )
    eml_path = os.path.normpath(eml_path)
    
    with open(eml_path, 'w', encoding='ascii') as f:
        f.write(HEADERS)
        f.write(b64_body)
    
    print(f"Written: {eml_path}")
    return eml_path


def analyze_eml(eml_path):
    with open(eml_path, 'rb') as f:
        msg = email.message_from_bytes(f.read())
    
    # Subject
    import email.header as eh
    subj_raw = msg.get('Subject', '')
    subj = ''.join(
        p.decode(c or 'utf-8') if isinstance(p, bytes) else p
        for p, c in eh.decode_header(subj_raw)
    )
    print(f"\nSubject: {subj}")
    
    # HTML body
    payload = msg.get_payload(decode=True)
    if payload:
        html = payload.decode('utf-8', errors='replace')
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        print(f"Tables found: {len(tables)}")
        for i, t in enumerate(tables):
            rows = t.find_all('tr')
            print(f"\nTable {i} ({len(rows)} rows):")
            for j, row in enumerate(rows[:3]):
                cells = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                print(f"  Row {j}: {cells}")


if __name__ == '__main__':
    path = create_eml()
    analyze_eml(path)
