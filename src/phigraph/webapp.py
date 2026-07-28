from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from .domains import DOMAIN_PROFILES
from .io import list_excel_sheets, load_table
from .modeling import AutoModelingAssistant
from .multifile_workflow import MultiFileConfig, run_multifile_modeling
from .analytical_workflow import (
    AnalyticalWorkflowConfig,
    run_analytical_multifile_workflow,
)
from .meta_workflow import MetaOperationalConfig, run_meta_operational_workflow
from .advanced_meta_workflow import AdvancedMetaConfig, run_advanced_meta_workflow
from .benchmark import (
    BenchmarkConfig,
    make_synthetic_fleet,
    make_synthetic_fraud,
    run_benchmark,
)
from .workflows import (
    AutoWorkflowConfig,
    WorkflowConfig,
    run_auto_analysis,
    run_local_analysis,
)


def _report_summary(report: dict) -> dict:
    artifacts = report.get("artifacts", {})
    simulation = artifacts.get("simulation", {})
    validation = artifacts.get("validation", {})
    return {
        "hotspot_nodes": artifacts.get("hotspot", []),
        "relative_drop": simulation.get("relative_drop"),
        "empirical_pvalue": simulation.get("empirical_pvalue"),
        "mode_overlap": simulation.get("mode_overlap"),
        "evidence_level": validation.get("evidence_level"),
        "warnings": validation.get("warnings", []),
    }


def _load_uploaded(uploaded, separator):
    suffix = Path(uploaded.name).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        uploaded.seek(0)
        sheets = list_excel_sheets(uploaded)
        uploaded.seek(0)
        # For v0.5, load the first sheet automatically in multi-file mode.
        return load_table(uploaded, filename=uploaded.name, sheet_name=sheets[0])
    return load_table(
        uploaded,
        filename=uploaded.name,
        csv_separator=separator,
    )


def main() -> None:
    st.set_page_config(
        page_title="PhiGraph Local Analyst",
        page_icon="◈",
        layout="wide",
    )
    st.title("PhiGraph Local Analyst")
    st.caption(
        "Modelado automático, multiarchivo y análisis causal-espectral local."
    )

    with st.sidebar:
        uploaded_files = st.file_uploader(
            "Cargar uno o varios CSV/Excel",
            type=["csv", "xlsx", "xlsm"],
            accept_multiple_files=True,
        )
        separator = st.selectbox("Separador CSV", [",", ";", "\t", "|"])

    if not uploaded_files:
        st.info("Carga uno o varios archivos para comenzar.")
        return

    tables = {}
    errors = []
    for uploaded in uploaded_files:
        try:
            loaded = _load_uploaded(uploaded, separator)
            name = Path(uploaded.name).stem
            if name in tables:
                name = f"{name}_{len(tables)+1}"
            tables[name] = loaded.frame
        except Exception as exc:
            errors.append(f"{uploaded.name}: {exc}")

    if errors:
        st.warning("Algunos archivos no pudieron cargarse:\n- " + "\n- ".join(errors))
    if not tables:
        return

    st.subheader("Archivos cargados")
    st.dataframe(
        [
            {"tabla": name, "filas": len(frame), "columnas": len(frame.columns)}
            for name, frame in tables.items()
        ],
        use_container_width=True,
    )

    benchmark_tab, advanced_meta_tab, meta_tab, analytical_tab, multifile_tab, single_tab = st.tabs(
        ["Benchmark formal v1.0", "Meta-learning avanzado v0.9", "Operación + meta-learning v0.8", "Análisis multiarchivo v0.6", "Modelo multiarchivo v0.5", "Análisis de una tabla"]
    )





    with benchmark_tab:
        st.write(
            "Compara PhiGraph y métodos base sobre datasets reproducibles con "
            "etiquetas y causas conocidas."
        )
        b1, b2, b3 = st.columns(3)
        with b1:
            benchmark_dataset = st.selectbox(
                "Dataset",
                ["fleet", "fraud"],
                key="benchmark_dataset",
            )
        with b2:
            benchmark_seed = st.number_input(
                "Semilla",
                min_value=1,
                max_value=100000,
                value=47,
            )
        with b3:
            benchmark_controls = st.number_input(
                "Controles PhiGraph",
                min_value=3,
                max_value=100,
                value=10,
            )

        if st.button(
            "Ejecutar benchmark formal v1.0",
            type="primary",
            use_container_width=True,
        ):
            try:
                dataset = (
                    make_synthetic_fleet(seed=int(benchmark_seed))
                    if benchmark_dataset == "fleet"
                    else make_synthetic_fraud(seed=int(benchmark_seed))
                )
                result = run_benchmark(
                    dataset,
                    BenchmarkConfig(
                        seed=int(benchmark_seed),
                        n_null_controls=int(benchmark_controls),
                    ),
                )
                st.session_state["benchmark_report"] = result.to_dict()
            except Exception as exc:
                st.error(f"El benchmark falló: {exc}")

        benchmark_report = st.session_state.get("benchmark_report")
        if benchmark_report:
            rows = []
            for method, payload in benchmark_report["methods"].items():
                rows.append({"method": method, **payload["metrics"]})
            st.subheader("Ranking")
            st.write(benchmark_report["ranking"])
            st.dataframe(rows, use_container_width=True)
            st.download_button(
                "Descargar reporte benchmark v1.0",
                data=json.dumps(benchmark_report, indent=2, default=float),
                file_name="phigraph_v1_benchmark_report.json",
                mime="application/json",
                use_container_width=True,
            )

    with advanced_meta_tab:
        st.write(
            "Validación cruzada temporal y selección UCB1 de la próxima configuración."
        )
        a1, a2, a3 = st.columns(3)
        with a1:
            adv_domain = st.selectbox(
                "Dominio",
                ["general"] + sorted(DOMAIN_PROFILES),
                key="adv_domain",
            )
        with a2:
            adv_controls = st.number_input(
                "Controles nulos base",
                min_value=5,
                max_value=200,
                value=30,
                step=5,
                key="adv_controls",
            )
        with a3:
            adv_exploration = st.slider(
                "Fuerza de exploración",
                min_value=0.1,
                max_value=5.0,
                value=2.0,
                step=0.1,
            )

        temporal_text = st.text_input(
            "Serie temporal para validación, separada por coma",
            key="adv_temporal",
        )
        adv_confirmed = st.checkbox(
            "Resultado operacional confirmado",
            key="adv_confirmed",
        )

        def _adv_numbers(text):
            return tuple(
                float(value.strip())
                for value in text.split(",")
                if value.strip()
            ) if text.strip() else ()

        if st.button(
            "Ejecutar meta-learning avanzado v0.9",
            type="primary",
            use_container_width=True,
        ):
            try:
                report = run_advanced_meta_workflow(
                    tables,
                    AdvancedMetaConfig(
                        domain=adv_domain,
                        meta_store_path="data/meta_learning.sqlite",
                        n_null_controls=int(adv_controls),
                        confirmed_outcome=adv_confirmed,
                        temporal_values=_adv_numbers(temporal_text),
                        exploration_strength=float(adv_exploration),
                    ),
                )
                st.session_state["advanced_meta_report"] = report
            except Exception as exc:
                st.error(f"El flujo v0.9 falló: {exc}")

        adv_report = st.session_state.get("advanced_meta_report")
        if adv_report:
            artifacts = adv_report.get("artifacts", {})
            cv = artifacts.get("temporal_cv", {})
            bandit = artifacts.get("contextual_bandit", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("CV temporal", f'{cv.get("mean_score", 0.0):.3f}')
            c2.metric("Sin fuga temporal", str(cv.get("leakage_guard", False)))
            c3.metric("Exploración", str(bandit.get("exploration", False)))
            st.subheader("Configuración seleccionada")
            st.json(bandit.get("selected_configuration", {}))
            st.subheader("Puntajes de brazos")
            st.json(bandit.get("arm_scores", {}))
            st.download_button(
                "Descargar reporte v0.9",
                data=json.dumps(adv_report, indent=2, default=float),
                file_name="phigraph_v09_advanced_meta_report.json",
                mime="application/json",
                use_container_width=True,
            )

    with meta_tab:
        st.write("Recomendaciones operacionales, evaluación antes/después y aprendizaje de configuraciones por dominio.")
        m1, m2, m3 = st.columns(3)
        with m1:
            meta_domain = st.selectbox("Dominio meta", ["general"] + sorted(DOMAIN_PROFILES), key="meta_domain")
        with m2:
            meta_signal = st.selectbox("Señal", ["structural_deviation","weighted_degree","clustering"], key="meta_signal")
        with m3:
            meta_controls = st.number_input("Controles nulos", 5, 200, 30, 5, key="meta_controls")
        before_text = st.text_input("Valores antes, separados por coma", key="meta_before")
        after_text = st.text_input("Valores después, separados por coma", key="meta_after")
        confirmed = st.checkbox("Resultado confirmado operacionalmente", value=False)
        def _numbers(text):
            return tuple(float(x.strip()) for x in text.split(",") if x.strip()) if text.strip() else ()
        if st.button("Ejecutar v0.8 y actualizar meta-learning", type="primary", use_container_width=True):
            try:
                report = run_meta_operational_workflow(
                    tables,
                    MetaOperationalConfig(
                        domain=meta_domain,
                        engineered_signal=meta_signal,
                        n_null_controls=int(meta_controls),
                        before_values=_numbers(before_text),
                        after_values=_numbers(after_text),
                        confirmed_outcome=confirmed,
                        meta_store_path="data/meta_learning.sqlite",
                    ),
                )
                st.session_state["meta_report"] = report
            except Exception as exc:
                st.error(f"El flujo v0.8 falló: {exc}")
        meta_report = st.session_state.get("meta_report")
        if meta_report:
            artifacts = meta_report.get("artifacts", {})
            meta = artifacts.get("meta_learning", {})
            perf = meta.get("performance", {})
            recs = artifacts.get("recommendations", {}).get("recommendations", [])
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Rendimiento total", f'{perf.get("total",0):.3f}')
            c2.metric("Evidencia", f'{perf.get("statistical",0):.3f}')
            c3.metric("Robustez", f'{perf.get("robustness",0):.3f}')
            c4.metric("Resultado", f'{perf.get("outcome",0):.3f}')
            st.subheader("Recomendaciones operacionales")
            st.dataframe(recs, use_container_width=True)
            st.subheader("Próxima configuración sugerida")
            st.json(meta.get("next_configuration", {}))
            st.download_button(
                "Descargar reporte v0.8",
                data=json.dumps(meta_report, indent=2, default=float),
                file_name="phigraph_v08_meta_report.json",
                mime="application/json",
                use_container_width=True,
            )

    with analytical_tab:
        st.write(
            "Construye el grafo heterogéneo, selecciona una proyección, "
            "genera señales, ejecuta controles nulos y desafía la estabilidad."
        )
        a1, a2, a3 = st.columns(3)
        with a1:
            analytical_overlap = st.slider(
                "Solapamiento mínimo",
                min_value=0.05,
                max_value=1.0,
                value=0.25,
                step=0.05,
                key="v06_overlap",
            )
        with a2:
            null_controls = st.number_input(
                "Controles nulos",
                min_value=5,
                max_value=200,
                value=30,
                step=5,
            )
        with a3:
            signal_method = st.selectbox(
                "Señal diseñada",
                ["structural_deviation", "weighted_degree", "clustering"],
            )

        if st.button(
            "Ejecutar análisis multiarchivo v0.6",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Ejecutando pipeline analítico y validación adversarial..."):
                try:
                    report = run_analytical_multifile_workflow(
                        tables,
                        AnalyticalWorkflowConfig(
                            min_join_overlap=float(analytical_overlap),
                            engineered_signal=signal_method,
                            n_null_controls=int(null_controls),
                        ),
                    )
                    st.session_state["analytical_report"] = report
                except Exception as exc:
                    st.error(f"El análisis v0.6 falló: {exc}")

        analytical_report = st.session_state.get("analytical_report")
        if analytical_report:
            artifacts = analytical_report.get("artifacts", {})
            projection = artifacts.get("projection", {})
            nulls = artifacts.get("null_controls", {})
            adversarial = artifacts.get("adversarial_validation", {})
            root = artifacts.get("projected_root_cause", {})

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Nodos proyectados", projection.get("retained_nodes", 0))
            r2.metric("IPR máximo", f'{root.get("dominant_ipr", 0.0):.4f}')
            r3.metric("p nulo", f'{nulls.get("empirical_pvalue", 1.0):.4f}')
            r4.metric(
                "Robustez",
                f'{adversarial.get("stability_score", 0.0):.3f}',
            )

            st.write("**Hotspot candidato:**", root.get("hotspot_nodes", []))
            if adversarial.get("warnings"):
                st.warning(
                    "Advertencias adversariales: "
                    + ", ".join(adversarial["warnings"])
                )

            with st.expander("Proyección seleccionada", expanded=True):
                st.json(projection)
            with st.expander("Señal diseñada"):
                st.json(artifacts.get("engineered_signal", {}))
            with st.expander("Selección del modelo"):
                st.json(artifacts.get("model_decision", {}))
            with st.expander("Controles nulos"):
                st.json(nulls)
            with st.expander("Validación adversarial"):
                st.json(adversarial)

            st.download_button(
                "Descargar reporte analítico v0.6",
                data=json.dumps(analytical_report, indent=2, default=float),
                file_name="phigraph_v06_analytical_report.json",
                mime="application/json",
                use_container_width=True,
            )

    with multifile_tab:
        min_overlap = st.slider(
            "Solapamiento mínimo para proponer uniones",
            min_value=0.05,
            max_value=1.0,
            value=0.25,
            step=0.05,
        )
        if st.button(
            "Catalogar y construir grafo heterogéneo",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Analizando esquemas y relaciones entre tablas..."):
                try:
                    report = run_multifile_modeling(
                        tables,
                        MultiFileConfig(min_join_overlap=float(min_overlap)),
                    )
                    st.session_state["multifile_report"] = report
                except Exception as exc:
                    st.error(f"El modelado multiarchivo falló: {exc}")

        report = st.session_state.get("multifile_report")
        if report:
            artifacts = report.get("artifacts", {})
            graph = artifacts.get("heterogeneous_graph", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("Nodos", graph.get("nodes", 0))
            c2.metric("Aristas", graph.get("edges", 0))
            c3.metric(
                "Uniones propuestas",
                len(artifacts.get("table_links", {}).get("join_candidates", [])),
            )

            with st.expander("Catálogo de tablas", expanded=True):
                st.json(artifacts.get("file_catalog", {}))
            with st.expander("Relaciones entre tablas"):
                st.json(artifacts.get("table_links", {}))
            with st.expander("Alineación temporal"):
                st.json(artifacts.get("temporal_alignment", {}))
            with st.expander("Grafo heterogéneo"):
                st.json(graph)

            st.download_button(
                "Descargar reporte multiarchivo",
                data=json.dumps(report, indent=2, default=float),
                file_name="phigraph_multifile_report.json",
                mime="application/json",
                use_container_width=True,
            )

    with single_tab:
        table_name = st.selectbox("Tabla a analizar", list(tables))
        frame = tables[table_name]
        st.dataframe(frame.head(100), use_container_width=True)

        automatic, manual = st.tabs(["Asistente automático", "Configuración manual"])

        with automatic:
            preferred_domain = st.selectbox(
                "Dominio preferido",
                ["auto"] + sorted(DOMAIN_PROFILES),
            )
            assistant = AutoModelingAssistant()
            proposal = assistant.propose(
                frame,
                preferred_domain=None if preferred_domain == "auto" else preferred_domain,
            )
            st.write(
                f"**Dominio propuesto:** {proposal.domain} "
                f"({proposal.domain_confidence:.1%})"
            )

            relation_labels = [
                f"{rel.source_column} → {rel.target_column} ({rel.confidence:.0%})"
                for rel in proposal.relations
            ]
            if relation_labels:
                relation_index = st.selectbox(
                    "Relación",
                    range(len(relation_labels)),
                    format_func=lambda i: relation_labels[i],
                )
                signal_choice = st.selectbox(
                    "Señal",
                    ["(ninguna)"] + list(proposal.signal_columns),
                )
                if st.button("Analizar modelo automático", use_container_width=True):
                    config = AutoWorkflowConfig(
                        preferred_domain=None if preferred_domain == "auto" else preferred_domain,
                        relation_index=int(relation_index),
                        signal_column=None if signal_choice == "(ninguna)" else signal_choice,
                    )
                    st.session_state["single_report"] = run_auto_analysis(frame, config)
            else:
                st.warning("No se infirió una relación utilizable.")

        with manual:
            columns = list(frame.columns)
            if len(columns) >= 2:
                source = st.selectbox("Origen", columns, index=0)
                target = st.selectbox("Destino", columns, index=1)
                if st.button("Analizar configuración manual", use_container_width=True):
                    st.session_state["single_report"] = run_local_analysis(
                        frame,
                        WorkflowConfig(source_column=source, target_column=target),
                    )

        single_report = st.session_state.get("single_report")
        if single_report:
            summary = _report_summary(single_report)
            st.json(summary)
            st.download_button(
                "Descargar reporte de análisis",
                data=json.dumps(single_report, indent=2, default=float),
                file_name="phigraph_analysis_report.json",
                mime="application/json",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
