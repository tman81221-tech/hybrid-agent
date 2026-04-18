import os
import pandas as pd
import json
import glob
import argparse
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="استخراج وتحليل الأدلة الرقمية من ملفات CSV و JSON")
    parser.add_argument(
        "--path",
        default=os.environ.get("APPLE_EVIDENCE_PATH", os.getcwd()),
        help="مسار مجلد الأدلة (الافتراضي: APPLE_EVIDENCE_PATH أو المجلد الحالي)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=500,
        dest="max_rows",
        help="الحد الأقصى لعدد الصفوف المعروضة من كل ملف CSV (الافتراضي: 500)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="مجلد حفظ التقرير (الافتراضي: نفس مجلد الأدلة)",
    )
    return parser.parse_args()


def run_autonomous_forensics(base_path, max_csv_rows, output_dir=None):
    all_findings = []
    error_logs = []
    processed = 0

    run_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out_dir = output_dir if output_dir else base_path
    os.makedirs(out_dir, exist_ok=True)
    report_output = os.path.join(
        out_dir,
        f"FINAL_EVIDENCE_REPORT_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    )

    target_files = (
        glob.glob(os.path.join(base_path, "*.csv")) +
        glob.glob(os.path.join(base_path, "*.json")) +
        glob.glob(os.path.join(base_path, "*.txt")) +
        glob.glob(os.path.join(base_path, "*.md"))
    )

    if not target_files:
        print("[!] لم يتم العثور على أي ملفات CSV أو JSON أو TXT أو MD في المسار المحدد.")
        return

    print(f"[!] جاري فحص {len(target_files)} ملفاً...")

    for file in target_files:
        file_name = os.path.basename(file)
        try:
            if file.endswith('.csv'):
                df = pd.read_csv(file, encoding='utf-8-sig')
                total_rows = len(df)
                truncated = total_rows > max_csv_rows
                display_df = df.head(max_csv_rows) if truncated else df

                header = f"\n{'='*20}\nFILE: {file_name} | Rows: {total_rows}"
                if truncated:
                    header += f" (عرض أول {max_csv_rows} سطر فقط)"
                header += f"\n{'='*20}"

                all_findings.append(header)
                all_findings.append(display_df.to_string(index=False))

            elif file.endswith('.json'):
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                all_findings.append(f"\n{'='*20}\nMETADATA: {file_name}\n{'='*20}")
                all_findings.append(json.dumps(data, indent=2, ensure_ascii=False))

            elif file.endswith('.txt') or file.endswith('.md'):
                with open(file, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                all_findings.append(f"\n{'='*20}\nFILE: {file_name}\n{'='*20}")
                all_findings.append(content)

            processed += 1

        except Exception as e:
            error_logs.append(f"  ⚠ {file_name}: {e}")

    with open(report_output, "w", encoding='utf-8') as f:
        f.write("=" * 47 + "\n")
        f.write("   تقرير الأدلة الرقمية المستخرج تلقائياً\n")
        f.write(f"   تاريخ الاستخراج : {run_ts}\n")
        f.write(f"   الملفات المعالجة: {processed} / {len(target_files)}\n")
        f.write("=" * 47 + "\n\n")

        f.write("\n".join(all_findings) if all_findings else "[!] لم يتم العثور على بيانات قابلة للتحليل.")

        if error_logs:
            f.write("\n\n" + "="*30 + "\nسجل الأخطاء:\n" + "="*30 + "\n")
            f.write("\n".join(error_logs))

    print(f"\n[✅] اكتملت المهمة — {processed}/{len(target_files)} ملف تمت معالجته.")
    print(f"[📂] {report_output}")


if __name__ == "__main__":
    args = parse_args()
    run_autonomous_forensics(args.path, args.max_rows, args.output)
