import os
import re
import glob
import pandas as pd


# Возможные варианты написания заголовка колонки со ссылкой
ID_COLUMN_CANDIDATES = ["sNO6x href", "sNO6x  href", "href"]


def find_id_column(df: pd.DataFrame) -> int | None:
    """Ищет индекс колонки, содержащей ссылки на объявления domclick."""
    # 1. По точному совпадению заголовка в первых строках
    for col_idx in df.columns:
        for row_idx in range(min(5, len(df))):
            cell = str(df.iat[row_idx, col_idx]).strip().lower()
            if cell in [c.lower() for c in ID_COLUMN_CANDIDATES]:
                return col_idx

    # 2. Fallback: ищем колонку, где большинство значений — ссылки на domclick card
    for col_idx in df.columns:
        col_vals = df[col_idx].dropna().astype(str)
        if len(col_vals) == 0:
            continue
        hits = col_vals.str.contains(r"/card/[a-z_]+__\d+", regex=True).sum()
        if hits >= max(1, len(col_vals) * 0.5):
            return col_idx

    return None


def extract_id_from_url(text: str) -> str | None:
    """Достаёт числовой id из URL объявления domclick."""
    if not isinstance(text, str):
        return None
    m = re.search(r"sale__flat__(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"/card/[a-z_]+__(\d+)", text)
    if m:
        return m.group(1)
    return None


def extract_features_from_text(text: str) -> dict:
    """Извлекает признаки (кроме id) из склеенного текста строки."""
    result = {
        "rooms": None,
        "area": None,
        "floor": None,
        "total_floors": None,
        "price": None,
    }
    if not isinstance(text, str):
        return result

    m = re.search(r"(\d+)\s*-\s*комн", text, re.IGNORECASE)
    if m:
        result["rooms"] = int(m.group(1))
    elif re.search(r"студи", text, re.IGNORECASE):
        result["rooms"] = 0

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*м[²2]", text)
    if m:
        result["area"] = float(m.group(1).replace(",", "."))

    m = re.search(r"(\d+)\s*/\s*(\d+)\s*эт", text)
    if m:
        result["floor"] = int(m.group(1))
        result["total_floors"] = int(m.group(2))

    m = re.search(r"([\d\s\u00a0\u202f]+)\s*₽", text)
    if m:
        price_str = re.sub(r"[\s\u00a0\u202f]", "", m.group(1))
        try:
            result["price"] = int(price_str)
        except ValueError:
            pass

    return result


def process_excel_file(path: str) -> pd.DataFrame:
    """Читает Excel-файл и возвращает DataFrame с id + признаками."""
    df = pd.read_excel(path, header=None, dtype=str)
    df = df.fillna("")

    id_col = find_id_column(df)
    if id_col is None:
        print(f"  ⚠ не найдена колонка со ссылкой в {os.path.basename(path)}")
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        id_value = extract_id_from_url(str(row.iloc[id_col]))
        if id_value is None:
            continue  # пропускаем строки без id (шапка, пустые и т.п.)

        # Для остальных признаков склеиваем все ячейки, КРОМЕ колонки со ссылкой
        other_text = " | ".join(
            str(v) for i, v in enumerate(row.values)
            if i != id_col and str(v).strip()
        )
        feats = extract_features_from_text(other_text)
        feats["id"] = id_value
        feats["source_file"] = os.path.basename(path)
        rows.append(feats)

    return pd.DataFrame(rows)


def main(folder: str, out_dir: str = "features", out_name: str = "all_features.csv"):
    files = glob.glob(os.path.join(folder, "*.xls*"))
    if not files:
        print(f"В папке '{folder}' не найдено Excel-файлов.")
        return

    os.makedirs(out_dir, exist_ok=True)

    all_frames = []
    for f in files:
        print(f"Обработка: {f}")
        try:
            df = process_excel_file(f)
            print(f"  → извлечено записей: {len(df)}")
            if not df.empty:
                all_frames.append(df)
        except Exception as e:
            print(f"  ⚠ ошибка: {e}")

    if not all_frames:
        print("Не удалось извлечь данные.")
        return

    result = pd.concat(all_frames, ignore_index=True)
    cols = ["id", "rooms", "area", "floor", "total_floors", "price", "source_file"]
    result = result[cols]

    if result["id"].notna().any():
        before = len(result)
        result = result.drop_duplicates(subset=["id"], keep="first")
        if before != len(result):
            print(f"Удалено дублей по id: {before - len(result)}")

    combined_path = os.path.join(out_dir, out_name)
    result.to_csv(combined_path, index=False, encoding="utf-8-sig")
    print(f"\nИтого сохранено {len(result)} строк в '{combined_path}'")


if __name__ == "__main__":
    main(folder="./data", out_dir="./features")
    