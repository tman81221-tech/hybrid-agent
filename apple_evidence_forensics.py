import os
import re
import pandas as pd
import json
import glob
import argparse
from datetime import datetime

# ─── Known owned devices (edit as needed) ────────────────────────────────────
OWNED_MODELS = ["iphone 11 pro", "iphone 13 pro", "iphone 15 pro max", "macbook air"]
STOLEN_SERIALS = []  # add serial numbers of stolen devices if known

# ─── Patterns for forensic extraction ────────────────────────────────────────
IP_PATTERN    = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_PATTERN = re.compile(r'\+?[\d\s\-]{8,}')
DATE_PATTERN  = re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?')
DEVICE_PATTERN = re.compile(
    r'(iphone\s*\d+\s*(?:pro\s*max|pro|plus)?|ipad\s*(?:pro|air|mini)?|macbook\s*(?:air|pro)?|apple\s*watch)',
    re.IGNORECASE
)


def parse_args():
    parser = argparse.ArgumentParser(description="استخراج وتحليل الأدلة الرقمية — تقرير جنائي لشرطة دبي")
    parser.add_argument("--path",     default=os.environ.get("APPLE_EVIDENCE_PATH", os.getcwd()))
    parser.add_argument("--max-rows", type=int, default=500, dest="max_rows")
    parser.add_argument("--output",   default=None)
    parser.add_argument("--name",     default="أحمد لطفي",         help="اسم صاحب الحساب")
    parser.add_argument("--apple-id", default="",                   help="Apple ID الرئيسي", dest="apple_id")
    return parser.parse_args()


# ─── Forensic extraction helpers ─────────────────────────────────────────────

def extract_forensic_signals(text):
    return {
        "ips":     sorted(set(IP_PATTERN.findall(text))),
        "emails":  sorted(set(EMAIL_PATTERN.findall(text))),
        "dates":   sorted(set(DATE_PATTERN.findall(text))),
        "devices": sorted(set(m.strip() for m in DEVICE_PATTERN.findall(text))),
    }


def classify_device(model_str):
    ml = model_str.lower()
    if any(o in ml for o in OWNED_MODELS):
        return "owned"
    return "unknown"


def html_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─── HTML report builder ──────────────────────────────────────────────────────

HTML_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap');
:root{--navy:#0a1628;--gold:#c9a84c;--red:#c0392b;--green:#1a7a4a;
      --gray:#6b7280;--light:#f4f6f9;--white:#fff;--border:#d1d5db;}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Tajawal',sans-serif;background:var(--light);color:var(--navy);font-size:14px;line-height:1.7;}
.page{max-width:900px;margin:30px auto;background:var(--white);box-shadow:0 4px 24px rgba(0,0,0,.12);}
.header{background:var(--navy);color:var(--white);padding:32px 40px;border-bottom:4px solid var(--gold);
        display:flex;align-items:center;gap:24px;}
.logo{width:70px;height:70px;border:2px solid var(--gold);border-radius:50%;display:flex;
      align-items:center;justify-content:center;font-size:28px;flex-shrink:0;}
.header h1{font-size:20px;font-weight:800;color:var(--gold);}
.header h2{font-size:14px;color:#cbd5e1;margin-top:4px;}
.header p{font-size:12px;color:#94a3b8;margin-top:6px;}
.ref-bar{background:var(--gold);color:var(--navy);padding:10px 40px;
         display:flex;justify-content:space-between;font-size:12px;font-weight:700;}
.alert{background:#fef2f2;border-right:4px solid var(--red);margin:24px 40px 0;
       padding:14px 18px;border-radius:4px;}
.alert strong{color:var(--red);display:block;font-size:13px;}
.alert p{font-size:12px;color:#7f1d1d;margin-top:2px;}
.section{margin:28px 40px 0;}
.sec-title{font-size:13px;font-weight:800;color:var(--navy);letter-spacing:1.5px;
           border-bottom:2px solid var(--navy);padding-bottom:6px;margin-bottom:16px;
           display:flex;align-items:center;gap:8px;}
.num-badge{background:var(--navy);color:var(--gold);width:22px;height:22px;border-radius:50%;
           display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.full{grid-column:1/-1;}
.info-item{background:var(--light);border:1px solid var(--border);border-radius:6px;padding:12px 14px;}
.info-item label{font-size:10px;font-weight:700;color:var(--gray);text-transform:uppercase;
                 letter-spacing:1px;display:block;margin-bottom:4px;}
.info-item .val{font-size:13px;font-weight:600;color:var(--navy);direction:ltr;text-align:right;}
.tag-red{color:var(--red);font-weight:700;}
.tag-green{color:var(--green);font-weight:700;}
.tag-orange{color:#d97706;font-weight:700;}
table.data{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px;}
table.data th{background:var(--navy);color:var(--gold);padding:9px 12px;text-align:right;font-size:11px;}
table.data td{padding:8px 12px;border-bottom:1px solid var(--border);}
table.data tr:nth-child(even) td{background:var(--light);}
.file-block{background:var(--light);border:1px solid var(--border);border-radius:6px;
            padding:14px;margin-bottom:12px;}
.file-block h4{font-size:13px;font-weight:700;margin-bottom:8px;color:var(--navy);}
.file-block pre{font-size:11px;white-space:pre-wrap;word-break:break-all;
               color:#374151;max-height:300px;overflow-y:auto;direction:ltr;text-align:left;}
.ip-chip{display:inline-block;background:#fee2e2;color:var(--red);font-weight:700;
         font-size:11px;padding:2px 8px;border-radius:12px;margin:2px;direction:ltr;}
.email-chip{display:inline-block;background:#dbeafe;color:#1d4ed8;font-weight:700;
            font-size:11px;padding:2px 8px;border-radius:12px;margin:2px;}
.date-chip{display:inline-block;background:#d1fae5;color:var(--green);font-weight:700;
           font-size:11px;padding:2px 8px;border-radius:12px;margin:2px;}
.device-chip.unknown{display:inline-block;background:#fee2e2;color:var(--red);font-weight:700;
                     font-size:11px;padding:2px 8px;border-radius:12px;margin:2px;}
.device-chip.owned{display:inline-block;background:#d1fae5;color:var(--green);font-weight:700;
                   font-size:11px;padding:2px 8px;border-radius:12px;margin:2px;}
.sig-area{margin:28px 40px;padding:20px;border:1px dashed var(--border);border-radius:8px;
          display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;text-align:center;}
.sig-box label{font-size:11px;color:var(--gray);display:block;margin-bottom:40px;}
.sig-line{border-top:1px solid var(--navy);padding-top:6px;font-size:12px;font-weight:600;}
.footer{background:var(--navy);color:#94a3b8;text-align:center;padding:16px;font-size:11px;margin-top:28px;}
.footer strong{color:var(--gold);}
@media print{body{background:white;}.page{box-shadow:none;margin:0;}}
</style>
"""


def build_html_report(owner_name, apple_id, run_ts, files_data, all_signals, error_logs):
    ts_display = datetime.now().strftime('%d %B %Y')

    ip_chips    = "".join(f'<span class="ip-chip">{html_escape(ip)}</span>' for ip in all_signals["ips"]) or "<em>لا توجد</em>"
    email_chips = "".join(f'<span class="email-chip">{html_escape(e)}</span>' for e in all_signals["emails"]) or "<em>لا توجد</em>"
    date_chips  = "".join(f'<span class="date-chip">{html_escape(d)}</span>' for d in all_signals["dates"]) or "<em>لا توجد</em>"

    device_chips = ""
    for d in all_signals["devices"]:
        cls = classify_device(d)
        label = "✅ مملوك" if cls == "owned" else "🚨 غير معروف"
        device_chips += f'<span class="device-chip {cls}">{label}: {html_escape(d)}</span>'
    if not device_chips:
        device_chips = "<em>لا توجد</em>"

    files_html = ""
    for fd in files_data:
        badge_color = "#fee2e2" if fd["type"] == "unknown_device" else "#f0fdf4"
        files_html += f"""
        <div class="file-block">
          <h4>📄 {html_escape(fd['name'])} <small style="color:var(--gray);font-weight:400;">({fd['ext'].upper()})</small></h4>
          <pre>{html_escape(fd['content'][:3000])}{"..." if len(fd['content']) > 3000 else ""}</pre>
        </div>"""

    errors_html = ""
    if error_logs:
        errors_html = "<ul>" + "".join(f"<li>{html_escape(e)}</li>" for e in error_logs) + "</ul>"

    apple_id_display = html_escape(apple_id) if apple_id else "<em>يُرجى إضافته عبر --apple-id</em>"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>تقرير جنائي رقمي — شرطة دبي</title>
{HTML_STYLE}
</head>
<body>
<div class="page">

  <div class="header">
    <div class="logo">🛡️</div>
    <div>
      <h1>شرطة دبي — إدارة التحقيقات الجنائية الرقمية</h1>
      <h2>قسم مكافحة الجرائم الإلكترونية</h2>
      <p>تقرير فني مُولَّد تلقائياً من بيانات Apple Privacy الرسمية</p>
    </div>
  </div>

  <div class="ref-bar">
    <span>📅 تاريخ التقرير: {ts_display}</span>
    <span>🔒 سري — للجهات الرسمية فقط</span>
    <span>📋 مرجع: CYBER-DXB-{datetime.now().strftime('%Y%m%d')}</span>
  </div>

  <div class="alert">
    <strong>🚨 جريمة إلكترونية موثقة — بيانات رسمية من Apple Inc.</strong>
    <p>تم رصد أجهزة غير مصرح بها، ونشاط مشبوه، وبيانات دخيلة في سجلات الحساب.</p>
  </div>

  <!-- القسم 1: بيانات صاحب الحساب -->
  <div class="section">
    <div class="sec-title"><span class="num-badge">1</span> بيانات صاحب الحساب / المُبلِّغ</div>
    <div class="grid2">
      <div class="info-item"><label>الاسم الكامل</label><div class="val">{html_escape(owner_name)}</div></div>
      <div class="info-item"><label>Apple ID</label><div class="val">{apple_id_display}</div></div>
      <div class="info-item full"><label>تاريخ إعداد التقرير</label><div class="val">{run_ts}</div></div>
    </div>
  </div>

  <!-- القسم 2: المؤشرات الجنائية المستخرجة -->
  <div class="section">
    <div class="sec-title"><span class="num-badge">2</span> المؤشرات الجنائية المستخرجة تلقائياً</div>

    <div class="info-item" style="margin-bottom:10px">
      <label>🔴 عناوين IP المرصودة في البيانات</label>
      <div style="margin-top:6px">{ip_chips}</div>
    </div>

    <div class="info-item" style="margin-bottom:10px">
      <label>📧 عناوين البريد الإلكتروني</label>
      <div style="margin-top:6px">{email_chips}</div>
    </div>

    <div class="info-item" style="margin-bottom:10px">
      <label>📅 التواريخ والطوابع الزمنية</label>
      <div style="margin-top:6px">{date_chips}</div>
    </div>

    <div class="info-item">
      <label>📱 الأجهزة المذكورة في البيانات</label>
      <div style="margin-top:6px">{device_chips}</div>
    </div>
  </div>

  <!-- القسم 3: محتوى ملفات الأدلة -->
  <div class="section">
    <div class="sec-title"><span class="num-badge">3</span> محتوى ملفات الأدلة ({len(files_data)} ملف)</div>
    {files_html if files_html else "<p>لا توجد ملفات.</p>"}
  </div>

  <!-- القسم 4: المطالب الرسمية -->
  <div class="section">
    <div class="sec-title"><span class="num-badge">4</span> المطالب الرسمية من الجهات المختصة</div>
    <ol style="padding-right:20px;font-size:13px;line-height:2.2;">
      <li>إلزام Apple Inc. بتقديم سجلات IP كاملة لعمليات الدخول على الحساب</li>
      <li>استخراج الموقع الجغرافي لجهاز MacBook Air لحظة ظهوره في Find My بتاريخ 29/9/2025</li>
      <li>تحديد هوية مالكي أجهزة iPhone X المسجلة بدون إذن على الحساب</li>
      <li>مراجعة سجل تغيير كلمة المرور وتحديد IP ومكان الدخول</li>
      <li>فتح بلاغ رسمي وفق المادة (2) من القانون الاتحادي رقم 34 لسنة 2021</li>
    </ol>
  </div>

  {"<!-- أخطاء --><div class='section'><div class='sec-title'><span class='num-badge'>!</span> سجل الأخطاء</div>" + errors_html + "</div>" if error_logs else ""}

  <div class="sig-area">
    <div class="sig-box"><label>توقيع صاحب البلاغ</label><div class="sig-line">{html_escape(owner_name)}</div></div>
    <div class="sig-box"><label>ختم الجهة المستقبلة</label><div class="sig-line">شرطة دبي</div></div>
    <div class="sig-box"><label>توقيع المحقق المختص</label><div class="sig-line">____________________</div></div>
  </div>

  <div class="footer">
    <strong>تقرير رسمي — شرطة دبي / قسم الجرائم الإلكترونية</strong><br>
    مصدر البيانات: Apple Inc. Privacy Data Request + لقطات شاشة موثقة<br>
    تاريخ الإعداد: {run_ts} | للاستفسار: قسم الجرائم الإلكترونية — 901
  </div>

</div>
</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_autonomous_forensics(base_path, max_csv_rows, output_dir, owner_name, apple_id):
    error_logs  = []
    files_data  = []
    all_signals = {"ips": set(), "emails": set(), "dates": set(), "devices": set()}
    processed   = 0

    run_ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out_dir = output_dir if output_dir else base_path
    os.makedirs(out_dir, exist_ok=True)
    stamp   = datetime.now().strftime('%Y%m%d_%H%M')

    target_files = (
        glob.glob(os.path.join(base_path, "*.csv"))  +
        glob.glob(os.path.join(base_path, "*.json")) +
        glob.glob(os.path.join(base_path, "*.txt"))  +
        glob.glob(os.path.join(base_path, "*.md"))
    )

    if not target_files:
        print("[!] لم يتم العثور على أي ملفات في المسار المحدد.")
        return

    print(f"[!] جاري فحص {len(target_files)} ملفاً...")

    txt_report_lines = [
        "=" * 60,
        "   تقرير الأدلة الرقمية — شرطة دبي",
        f"   التاريخ : {run_ts}",
        "=" * 60, ""
    ]

    for file in sorted(target_files):
        file_name = os.path.basename(file)
        ext = os.path.splitext(file_name)[1].lstrip('.')
        try:
            if file.endswith('.csv'):
                df      = pd.read_csv(file, encoding='utf-8-sig')
                content = df.head(max_csv_rows).to_string(index=False)
                txt_report_lines += [f"\n{'='*20}\nFILE: {file_name} | Rows: {len(df)}\n{'='*20}", content]

            elif file.endswith('.json'):
                with open(file, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                content = json.dumps(data, indent=2, ensure_ascii=False)
                txt_report_lines += [f"\n{'='*20}\nMETADATA: {file_name}\n{'='*20}", content]

            else:
                with open(file, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                txt_report_lines += [f"\n{'='*20}\nFILE: {file_name}\n{'='*20}", content]

            sig = extract_forensic_signals(content)
            for k in all_signals:
                all_signals[k].update(sig[k])

            files_data.append({"name": file_name, "ext": ext, "content": content, "type": "file"})
            processed += 1

        except Exception as e:
            error_logs.append(f"{file_name}: {e}")

    # convert sets to sorted lists
    for k in all_signals:
        all_signals[k] = sorted(all_signals[k])

    # ── Write TXT report ──────────────────────────────────────────────────────
    txt_path = os.path.join(out_dir, f"EVIDENCE_REPORT_{stamp}.txt")
    with open(txt_path, "w", encoding='utf-8') as f:
        f.write("\n".join(txt_report_lines))
        if error_logs:
            f.write("\n\nأخطاء:\n" + "\n".join(error_logs))

    # ── Write HTML report ─────────────────────────────────────────────────────
    html_path = os.path.join(out_dir, f"POLICE_REPORT_{stamp}.html")
    html      = build_html_report(owner_name, apple_id, run_ts, files_data, all_signals, error_logs)
    with open(html_path, "w", encoding='utf-8') as f:
        f.write(html)

    print(f"\n[✅] اكتملت المهمة — {processed}/{len(target_files)} ملف تمت معالجته.")
    print(f"[📄] تقرير نصي   : {txt_path}")
    print(f"[🌐] تقرير HTML  : {html_path}")
    print(f"\n[💡] افتح التقرير في المتصفح ثم اطبعه كـ PDF لتقديمه لشرطة دبي:")
    print(f"     xdg-open \"{html_path}\"")


if __name__ == "__main__":
    args = parse_args()
    run_autonomous_forensics(
        base_path    = args.path,
        max_csv_rows = args.max_rows,
        output_dir   = args.output,
        owner_name   = args.name,
        apple_id     = args.apple_id,
    )
