"""Минимальный интерфейс. Качественный агент с retry."""
import tempfile
from pathlib import Path

import streamlit as st

from agent import run_quick, run_full

st.set_page_config(page_title="AI Недвижимость", page_icon="🏠", layout="centered")

st.title("Оценка квартиры по фото")
uploaded = st.file_uploader("Фото комнаты", type=["jpg", "jpeg", "png"])

mode = st.radio("Режим", ["Быстрая оценка (~15 сек)", "Полный пайплайн (стейджинг)"], horizontal=True)
prompt = st.text_input("Что изменить?", "Replace sofa with modern gray sofa") if "Полный" in mode else None

if st.button("Запустить"):
    if not uploaded:
        st.error("Загрузи фото")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as f:
            f.write(uploaded.getvalue())
            path = f.name

        out_path = tempfile.mktemp(suffix=".jpg") if "Полный" in mode else None
        try:
            if "Быстрая" in mode:
                with st.spinner("Анализ..."):
                    r = run_quick(path)
                st.image(uploaded, use_container_width=True)
                s = r["score"]
                st.metric("Оценка", f"{s.get('overall_score', 0)}/10")
                st.write(r["report"])
                st.json({k: v for k, v in s.items() if k != "summary"})
            else:
                with st.spinner("Выполняется пайплайн..."):
                    r = run_full(path, prompt or "", out_path)
                col1, col2 = st.columns(2)
                with col1:
                    st.image(uploaded, caption="До", use_container_width=True)
                    st.metric("До", f"{r['score_before'].get('overall_score', 0)}/10")
                with col2:
                    if Path(out_path or "").exists():
                        st.image(out_path, caption="После", use_container_width=True)
                        sa = r.get("score_after") or {}
                        st.metric("После", f"{sa.get('overall_score', 0)}/10")
                st.write(r["report"])
        except Exception as e:
            st.error(str(e))
        finally:
            Path(path).unlink(missing_ok=True)
            if out_path:
                Path(out_path).unlink(missing_ok=True)
