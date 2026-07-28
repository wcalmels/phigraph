from io import BytesIO

import pandas as pd

from phigraph.io import load_table


def test_load_csv_upload():
    source = BytesIO(b"source,target,weight\na,b,1\n")
    loaded = load_table(source, filename="sample.csv")
    assert list(loaded.frame.columns) == ["source", "target", "weight"]
    assert len(loaded.frame) == 1


def test_load_excel_upload():
    buffer = BytesIO()
    pd.DataFrame({"source": ["a"], "target": ["b"]}).to_excel(
        buffer, index=False, engine="openpyxl"
    )
    buffer.seek(0)
    loaded = load_table(buffer, filename="sample.xlsx")
    assert len(loaded.frame) == 1
