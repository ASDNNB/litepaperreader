from __future__ import annotations

import hashlib
import io
from typing import Iterator

from litepaperreader.adapters.base import FormatAdapter
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell, ContentType, SourceRef, SourceSpan, StructureMeta


class TableAdapter(FormatAdapter):
    """Convert tabular data (CSV, XLSX, Parquet) to TABLE Cell stream."""

    def can_handle(self, ref: ResourceRef) -> bool:
        ext = ref.resource_path.rsplit(".", 1)[-1].lower()
        return ext in ("csv", "xlsx", "xls", "parquet", "tsv")

    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        checksum = hashlib.sha256(raw).hexdigest()[:16]
        source_ref = SourceRef(
            connector=ref.connector,
            resource_path=ref.resource_path,
            resource_checksum=checksum,
        )
        try:
            import pandas as pd
            ext = ref.resource_path.rsplit(".", 1)[-1].lower()
            if ext == "csv":
                df = pd.read_csv(io.BytesIO(raw))
            elif ext == "tsv":
                df = pd.read_csv(io.BytesIO(raw), sep="\t")
            elif ext in ("xlsx", "xls"):
                df = pd.read_excel(io.BytesIO(raw))
            elif ext == "parquet":
                df = pd.read_parquet(io.BytesIO(raw))
            else:
                return
        except ImportError:
            return

        schema = {col: str(dtype) for col, dtype in df.dtypes.items()}

        # One Cell per row
        for idx, (_, row) in enumerate(df.iterrows()):
            row_dict = row.dropna().to_dict()
            body = " | ".join(f"{k}: {v}" for k, v in row_dict.items())
            yield Cell(
                id=f"{ref.connector}:{checksum}:row:{idx:06d}",
                source=SourceRef(
                    connector=ref.connector,
                    resource_path=ref.resource_path,
                    resource_checksum=checksum,
                    span=SourceSpan(idx, idx + 1),
                ),
                content_type=ContentType.TABLE,
                body=body,
                structure=StructureMeta(
                    content_type=ContentType.TABLE,
                    schema=schema,
                ),
                metadata={"row_index": idx, "columns": list(row_dict.keys())},
            )

        # Schema Cell with column info
        col_info = "; ".join(f"{col}: {dtype}" for col, dtype in schema.items())
        yield Cell(
            id=f"{ref.connector}:{checksum}:schema",
            source=SourceRef(
                connector=ref.connector,
                resource_path=ref.resource_path,
                resource_checksum=checksum,
            ),
            content_type=ContentType.TABLE,
            body=f"Table with {len(df)} rows, columns: {col_info}",
            structure=StructureMeta(
                content_type=ContentType.TABLE,
                schema=schema,
                hierarchy_level=0,
            ),
            metadata={
                "num_rows": len(df),
                "num_columns": len(schema),
                "columns": list(schema.keys()),
            },
        )
