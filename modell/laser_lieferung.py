"""Build the delivery folder with Japanese file names (PDF + SVG backup + instruction sheet).

Usage: python3 laser_lieferung.py <laser_v1_dir> <target_dir>
File names avoid kana with dakuten so they display the same on FAT32 sticks under Windows.
"""
import csv
import pathlib
import shutil
import sys

KIND = {"floor": "底板", "side": "側板", "strip": "断面", "cross": "横材"}
SIDE = {"S-L": "左", "S-R": "右"}

ANLEITUNG = """斜面模型　レーザー切断データ（2026年11月12日）

■ 材料
木の板　厚さ2 mm、600 × 300 mm
使用枚数：本番{n}枚（テスト片は端材で切ります）
完成サイズ：幅300 × 奥行280.6 × 高さ271.4 mm

■ 線の色（PDFとSVGは同じ内容です）
赤（RGB 255,0,0、線幅0.1 pt）＝切断のみ（彫刻・文字はありません）
データは600 × 300 mmで、部品は左上から並んでいます。右側の余白は次に使えます。
必ず100 %（実寸）で読み込んでください。「用紙に合わせる」は使わないでください。

■ 切る順番
1ファイル＝板1枚です。1枚ずつ順番に切ります。

1. 00_最初に切る_テスト_スリット幅.pdf
   小さなテスト片です（左上の小さな部品だけ、端材で切ってください）。
   左から順番に6つのスリット（1.7、1.8、1.9、2.0、2.1、2.2 mm）があります。
   同じ板の端材を差し込み、しっかり固定されるスリットを確認してください。
   左から3番目（1.9 mm）がちょうど良い場合 → そのまま01〜{last}を切ってください。
   ほかのスリットの場合 → 切る前に連絡してください。データを作り直します。

2. 01〜{last}を番号順に切ります。

■ 1枚の板の中の順番
① 内側の赤（スリット・穴）
② 外側の赤（外形）
外形を先に切ると部品が動き、スリットの位置がずれます。

■ 注意
・本番の前に端材で出力と速度を確認してください。
・板が反らないように、四隅を重しかテープで固定してください。
・部品が落ちない場合は、板を動かさずにもう一度切ってください。

■ 部品（合計24個）
B　　　　　底板 1枚
S-L、S-R　 側板 2枚（左右の外側）
P01〜P16　 断面 16枚（斜面の波の形、幅約2〜3 cm、LED配線のため裏側は空いています）
Q1〜Q5　　 横材 5本（断面をまっすぐ立たせます）

------------------------------------------------------------
Deutsch (Kurzfassung)

Material: 2 mm Holz, 600 x 300 mm, {n} Platten. Die Testleiste auf einem Reststück schneiden.
Fertiges Modell: 300 x 280,6 x 271,4 mm.
Rot = schneiden (0,1 pt Linie), keine Gravur/Beschriftung. Immer 100 %, nie "an Seite anpassen".
Die Teile liegen ab links oben, der freie Rest bleibt rechts.
Reihenfolge: zuerst 00 (Schlitz-Testleiste, 6 Schlitze von links nach rechts: 1,7 bis 2,2 mm). Hält der 3. Schlitz von links (1,9 mm) fest, dann 01 bis {last} der Reihe nach.
Passt ein anderer Schlitz, vor dem Schneiden melden, die Dateien werden neu erzeugt.
Je Platte: erst innere Schnitte (Schlitze/Löcher), zuletzt die Außenkontur.
"""


def name_for(board, parts, kinds):
    groups = []
    for kind in ("floor", "side", "strip", "cross"):
        ids = sorted(p for p in parts if kinds[p] == kind)
        if not ids:
            continue
        if kind == "side":
            groups.append(f"{KIND[kind]}_{SIDE[ids[0]]}_{ids[0]}")
        else:
            groups.append(KIND[kind] + "_" + "_".join(ids))
    return f"{board:02d}_" + "_".join(groups)


def main():
    src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    rows = list(csv.DictReader(open(src / "teileliste.csv")))
    kinds = {r["teil"]: r["art"] for r in rows}
    boards = {}
    for r in rows:
        boards.setdefault(int(r["brett"]), []).append(r["teil"])
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    (dst / "SVG_予備").mkdir(parents=True, exist_ok=True)
    pairs = [("schlitz_testleiste", "00_最初に切る_テスト_スリット幅")]
    pairs += [(f"brett_{b:02d}", name_for(b, boards[b], kinds)) for b in sorted(boards)]
    for old, new in pairs:
        shutil.copyfile(src / "pdf" / f"{old}.pdf", dst / f"{new}.pdf")
        shutil.copyfile(src / f"{old}.svg", dst / "SVG_予備" / f"{new}.svg")
        print(f"{old} -> {new}")
    n = len(boards)
    (dst / "00_作業手順.txt").write_text(ANLEITUNG.format(n=n, last=f"{n:02d}"), encoding="utf-8")


main()
