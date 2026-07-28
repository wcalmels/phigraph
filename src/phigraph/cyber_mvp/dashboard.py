from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

import pandas as pd
import streamlit as st

from .demo_data import generate_demo_events
from .detector import CyberShadowDetector
from .metrics import compute_cyber_metrics
from .schema import validate_events
from .store import CyberMVPStore


def _load_uploaded(uploaded) -> pd.DataFrame:
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".json":
        payload = json.load(uploaded)
        if isinstance(payload, dict) and "events" in payload:
            payload = payload["events"]
        return pd.DataFrame(payload)
    uploaded.seek(0)
    try:
        return pd.read_csv(uploaded)
    except Exception:
        uploaded.seek(0)
        return pd.read_csv(uploaded, sep=";")


def main() -> None:
    st.set_page_config(
        page_title="PhiGraph Cyber Shadow MVP",
        page_icon="◈",
        layout="wide",
    )
    st.title("PhiGraph Cyber Shadow MVP")
    st.caption(
        "Análisis relacional de eventos de seguridad. "
        "Observa y recomienda; no ejecuta acciones reales."
    )

    store_path = Path(
        st.sidebar.text_input(
            "Archivo local de resultados",
            "data/cyber_mvp_store.json",
        )
    )
    store = CyberMVPStore(store_path)

    source = st.sidebar.radio(
        "Fuente de datos",
        ["Demo incluida", "Cargar CSV/JSON"],
    )
    if source == "Demo incluida":
        frame = generate_demo_events()
        st.sidebar.success(
            "Dataset sintético con una secuencia de ataque incluida."
        )
    else:
        uploaded = st.sidebar.file_uploader(
            "Eventos de seguridad",
            type=["csv", "json"],
        )
        if uploaded is None:
            st.info("Carga un CSV o JSON para comenzar.")
            return
        try:
            frame = _load_uploaded(uploaded)
        except Exception as exc:
            st.error(f"No fue posible leer el archivo: {exc}")
            return

    top_k = st.sidebar.slider(
        "Número máximo de alertas",
        min_value=3,
        max_value=25,
        value=10,
    )

    normalized, validation = validate_events(frame)
    col1, col2, col3 = st.columns(3)
    col1.metric("Eventos", len(frame))
    col2.metric(
        "Usuarios",
        normalized["user_id"].nunique()
        if "user_id" in normalized
        else 0,
    )
    col3.metric(
        "Dispositivos",
        normalized["device_id"].nunique()
        if "device_id" in normalized
        else 0,
    )

    with st.expander("Contrato de datos", expanded=not validation.valid):
        st.json(validation.to_dict())

    if not validation.valid:
        st.error(
            "El archivo no cumple el contrato mínimo de ciberseguridad."
        )
        st.dataframe(frame.head(25), use_container_width=True)
        return

    st.subheader("Vista previa de eventos")
    st.dataframe(
        normalized.tail(30),
        use_container_width=True,
        hide_index=True,
    )

    if st.button(
        "Ejecutar análisis shadow",
        type="primary",
        use_container_width=True,
    ):
        run_id = str(uuid.uuid4())
        result = CyberShadowDetector(top_k=top_k).analyze(normalized)
        store.save_run(run_id, result.to_dict())
        st.session_state["cyber_run_id"] = run_id
        st.session_state["cyber_result"] = result.to_dict()

    result = st.session_state.get("cyber_result")
    run_id = st.session_state.get("cyber_run_id")
    if result:
        st.divider()
        st.subheader("Resultado shadow")
        graph = result["graph_summary"]
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Nodos", graph.get("nodes", 0))
        g2.metric("Relaciones", graph.get("edges", 0))
        g3.metric("Alertas", len(result["alerts"]))
        g4.metric("Acciones ejecutadas", "0")

        alerts = pd.DataFrame(result["alerts"])
        if alerts.empty:
            st.success("No se localizaron anomalías sobre el umbral.")
        else:
            st.dataframe(
                alerts[
                    [
                        "severity",
                        "entity_type",
                        "entity",
                        "anomaly_score",
                        "confidence",
                        "recommendation",
                        "evidence",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Revisión del analista")
            selected = st.selectbox(
                "Alerta",
                result["alerts"],
                format_func=lambda row: (
                    f"{row['severity'].upper()} — "
                    f"{row['entity_type']}:{row['entity']} "
                    f"({row['anomaly_score']:.3f})"
                ),
            )
            analyst = st.text_input(
                "Analista",
                value="analyst-demo",
            )
            verdict = st.selectbox(
                "Veredicto",
                [
                    "confirmed",
                    "false_positive",
                    "deferred",
                    "insufficient_evidence",
                ],
            )
            notes = st.text_area("Notas")
            if st.button("Guardar feedback"):
                store.add_feedback(
                    run_id=run_id,
                    alert_id=selected["alert_id"],
                    analyst=analyst,
                    verdict=verdict,
                    notes=notes,
                )
                st.success("Feedback registrado.")

    st.divider()
    st.subheader("Métricas acumuladas")
    metrics = compute_cyber_metrics(store.list_feedback())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Revisadas", metrics["reviewed_alerts"])
    m2.metric("Confirmadas", metrics["confirmed_alerts"])
    m3.metric(
        "Precisión",
        (
            f"{metrics['precision']:.1%}"
            if metrics["precision"] is not None
            else "Sin datos"
        ),
    )
    m4.metric(
        "Falsos positivos",
        (
            f"{metrics['false_positive_rate']:.1%}"
            if metrics["false_positive_rate"] is not None
            else "Sin datos"
        ),
    )

    st.caption(
        "Estado operacional: SHADOW. "
        "Las recomendaciones no modifican identidades, endpoints, "
        "firewalls ni ningún sistema externo."
    )
