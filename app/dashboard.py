"""SpO2 AI Eval Pipeline — Streamlit Dashboard.

Six views + interactive pipeline runner.
Run: streamlit run app/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_gen.synthetic import NightTrace, generate_dataset, generate_baby_cohort, generate_trace
from src.rules.tier1_engine import run_tier1, apply_rules
from src.patterns.feature_eng import build_feature_matrix
from src.patterns.miner import run_pattern_mining, FEATURE_COLS
from src.classifier.tier2 import train_tier2, predict_tier2
from src.classifier.expert_sim import run_expert_queue
from src.handoff.generator import generate_handoff
from src.evals.clinical_accuracy import evaluate_clinical_accuracy
from src.evals.handoff_quality import evaluate_handoff_quality
from src.evals.artifact_handling import evaluate_artifact_handling
from src.evals.base import EvalResult
from src.llm_utils import get_tracker, reset_tracker
from app.components.trace_viewer import plot_trace
from app.theme import (
    TEAL_DARK, TEAL_PRIMARY, TEAL_LIGHT, SAGE, SAGE_BG,
    CREAM_BG, WARM_WHITE, BODY_TEXT, MUTED_TEXT, BORDER,
    URGENT_RED, AMBER, NEUTRAL_GRAY,
    FONT_HEADING, FONT_BODY,
    TIER_COLORS, FUNNEL_COLORS, LABEL_COLORS, EVAL_COLORS,
    URGENCY_COLORS, PLOTLY_LAYOUT, GLOBAL_CSS,
    section_card, metric_card_html, page_intro_html,
    urgency_badge_html, detail_row_html,
)


st.set_page_config(
    page_title="SpO2 AI Eval Pipeline",
    page_icon="🫁",
    layout="wide",
)

# Inject global CSS from theme
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# Header
st.markdown(
    f'<h1 style="margin-bottom: 2px; font-size: 2rem;">Neonatal SpO2 '
    f'<em style="font-style:italic;">AI Eval</em> Pipeline</h1>',
    unsafe_allow_html=True,
)
st.caption("Portfolio demo — synthetic data, multi-tier triage, LLM evals")


# ---------------------------------------------------------------------------
# Session state: run the pipeline once, cache results
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Running pipeline (Phases 1-4)...")
def _run_phases_1_4(n_babies: int, nights: int, seed: int):
    """Run Phases 1-4 and return serializable results."""
    traces = generate_dataset(n_babies, nights, seed)
    tier1_results, unlabeled = run_tier1(traces)

    all_df = build_feature_matrix(traces, tier1_results)
    candidate_rules, tree = run_pattern_mining(all_df)

    model, le, metrics = train_tier2(tier1_results, traces)
    tier2_results = predict_tier2(model, le, unlabeled)

    expert_traces = [
        t for t in unlabeled
        for r in tier2_results
        if r.trace_id == t.night_id and r.routed_to == "expert_queue"
    ]
    expert_results = run_expert_queue(expert_traces, tier2_results, seed=seed)

    # Build final label map
    final_labels = {}
    final_sources = {}
    for r in tier1_results:
        if r.auto_labeled:
            final_labels[r.trace_id] = r.label
            final_sources[r.trace_id] = "Tier 1 (rules)"
    for r in tier2_results:
        if r.routed_to == "auto":
            final_labels[r.trace_id] = r.predicted_label
            final_sources[r.trace_id] = "Tier 2 (classifier)"
    for r in expert_results:
        final_labels[r.trace_id] = r.expert_label
        final_sources[r.trace_id] = "Expert review"

    return (traces, tier1_results, tier2_results, expert_results,
            candidate_rules, tree, metrics, final_labels, final_sources, all_df)


def _run_evals_mock(traces, final_labels, handoffs_map, seed=42):
    """Run mock evals on all traces."""
    rng = np.random.default_rng(seed)
    results = []
    for trace in traces:
        label = final_labels.get(trace.night_id, "normal")
        s = int(rng.integers(0, 2**31))

        results.append(evaluate_clinical_accuracy(
            trace, label, use_llm=False, seed=s))

        handoff = handoffs_map.get(trace.night_id)
        if handoff:
            results.append(evaluate_handoff_quality(
                trace, handoff, label, use_llm=False, seed=s+1))

        results.append(evaluate_artifact_handling(
            trace, label, use_llm=False, seed=s+2))

    return results


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.markdown(
    f'<p style="font-family: {FONT_HEADING}; font-size:1.3rem; '
    f'font-weight:600; color:{TEAL_DARK} !important; margin-bottom:2px;">'
    f'SpO2 Pipeline</p>',
    unsafe_allow_html=True,
)
st.sidebar.caption("Neonatal monitoring demo")
page = st.sidebar.radio("View", [
    "Pipeline Overview",
    "Pre-Annotation Coverage",
    "Rule Discovery",
    "Eval Scores",
    "Sample Handoffs",
    "Run Single Trace",
    "Design System",
])

st.sidebar.markdown("---")
st.sidebar.subheader("Dataset Settings")
n_babies = st.sidebar.slider("Babies", 10, 200, 100)
nights = st.sidebar.slider("Nights per baby", 1, 5, 3)
seed = st.sidebar.number_input("Random seed", value=42)

# Run pipeline
data = _run_phases_1_4(n_babies, nights, int(seed))
(traces, tier1_results, tier2_results, expert_results,
 candidate_rules, tree, classifier_metrics, final_labels, final_sources, features_df) = data

# Generate mock handoffs
handoffs_map = {}
for trace in traces:
    label = final_labels.get(trace.night_id, "normal")
    handoffs_map[trace.night_id] = generate_handoff(trace, label, use_llm=False)


# ---------------------------------------------------------------------------
# Page: Pipeline Overview
# ---------------------------------------------------------------------------

if page == "Pipeline Overview":
    st.header("Pipeline Overview")

    total = len(traces)
    t1 = sum(1 for r in tier1_results if r.auto_labeled)
    t2 = sum(1 for r in tier2_results if r.routed_to == "auto")
    eq = len(expert_results)

    # Compute accuracy for the intro
    t1_correct = sum(1 for r in tier1_results if r.auto_labeled and r.label == r.ground_truth)
    t1_acc = t1_correct / t1 * 100 if t1 else 0

    st.markdown(page_intro_html(
        f"Three-tier triage system processed <strong>{total}</strong> overnight SpO2 traces. "
        f"Rules auto-labeled {t1/total*100:.0f}% of traces at {t1_acc:.0f}% accuracy, "
        f"the classifier handled {t2/total*100:.0f}%, and {eq/total*100:.0f}% routed to expert review."
    ), unsafe_allow_html=True)

    # Custom metric cards with accent bars
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(metric_card_html("Total Traces", str(total),
                    accent_color=TEAL_DARK), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card_html("Tier 1 (Rules)", f"{t1}",
                    accent_color=TEAL_PRIMARY,
                    delta=f"{t1/total*100:.0f}% of total"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card_html("Tier 2 (ML)", f"{t2}",
                    accent_color=SAGE,
                    delta=f"{t2/total*100:.0f}% of total"), unsafe_allow_html=True)
    with col4:
        st.markdown(metric_card_html("Expert Queue", f"{eq}",
                    accent_color=AMBER,
                    delta=f"{eq/total*100:.0f}% of total"), unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Two-column layout: accuracy chart + pie chart, wrapped in section cards
    left_col, right_col = st.columns(2)

    with left_col:
        tier_data = []
        for r in tier1_results:
            if r.auto_labeled:
                tier_data.append({"Tier": "Tier 1 (Rules)", "Correct": r.label == r.ground_truth})
        for r in tier2_results:
            if r.routed_to == "auto":
                tier_data.append({"Tier": "Tier 2 (ML)", "Correct": r.predicted_label == r.ground_truth})
        for r in expert_results:
            tier_data.append({"Tier": "Expert Review", "Correct": r.expert_label == r.ground_truth})

        tier_df = pd.DataFrame(tier_data)
        if not tier_df.empty:
            acc = tier_df.groupby("Tier")["Correct"].mean().reset_index()
            acc.columns = ["Tier", "Accuracy"]
            acc["Accuracy"] = (acc["Accuracy"] * 100).round(1)

            fig_acc = go.Figure(go.Bar(
                x=acc["Accuracy"],
                y=acc["Tier"],
                orientation="h",
                marker=dict(
                    color=TIER_COLORS,
                    line=dict(width=0),
                ),
                text=[f"{v:.1f}%" for v in acc["Accuracy"]],
                textposition="auto",
                textfont=dict(color="white", size=14, family=FONT_BODY),
            ))
            fig_acc.update_layout(
                **PLOTLY_LAYOUT,
                title=dict(text="Accuracy by Tier", font=dict(
                    family=FONT_HEADING, size=16, color=TEAL_DARK)),
                height=240,
                xaxis=dict(range=[0, 105], title="", gridcolor=BORDER,
                           showline=False, zeroline=False),
                yaxis=dict(autorange="reversed", showgrid=False),
                showlegend=False,
            )
            st.plotly_chart(fig_acc, use_container_width=True, key="acc_chart")

    with right_col:
        gt_counts = Counter(t.ground_truth_label for t in traces)
        label_order = ["normal", "borderline", "urgent", "artifact"]
        ordered_labels = [l for l in label_order if l in gt_counts]

        fig_pie = go.Figure(go.Pie(
            labels=[l.capitalize() for l in ordered_labels],
            values=[gt_counts[l] for l in ordered_labels],
            marker=dict(
                colors=[LABEL_COLORS[l] for l in ordered_labels],
                line=dict(color=WARM_WHITE, width=2),
            ),
            hole=0.5,
            textinfo="percent",
            textfont=dict(size=13, family=FONT_BODY, color="white"),
            hoverinfo="label+value+percent",
        ))
        fig_pie.update_layout(
            **PLOTLY_LAYOUT,
            title=dict(text="Ground Truth Distribution", font=dict(
                family=FONT_HEADING, size=16, color=TEAL_DARK)),
            height=340,
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5,
                font=dict(family=FONT_BODY, size=12, color=TEAL_DARK),
            ),
            annotations=[dict(
                text=f"<b>{total}</b><br><span style='font-size:11px'>traces</span>",
                x=0.5, y=0.5, font=dict(size=18, color=TEAL_DARK, family=FONT_HEADING),
                showarrow=False,
            )],
        )
        st.plotly_chart(fig_pie, use_container_width=True, key="pie_chart")

    # Coverage funnel in a section card
    st.markdown(f"""
    <div style="background:{WARM_WHITE}; border:1px solid {BORDER};
    border-radius:14px; padding:24px; margin-top:4px;
    box-shadow:0 1px 6px rgba(44,95,91,0.05);">
    <div style="font-family:{FONT_HEADING}; color:{TEAL_DARK};
    font-weight:500; font-size:1.15rem; margin-bottom:4px;">Triage Funnel</div>
    <div style="color:{MUTED_TEXT}; font-size:0.8rem; margin-bottom:12px;
    font-family:{FONT_BODY};">How traces flow through the three classification tiers</div>
    <div style="border-bottom:1px solid {BORDER}; margin-bottom:16px;"></div>
    """, unsafe_allow_html=True)

    fig_funnel = go.Figure(go.Funnel(
        y=["All Traces", "Tier 1 Auto-labeled", "Tier 2 Auto-labeled", "Expert Queue"],
        x=[total, t1, t2, eq],
        marker=dict(color=FUNNEL_COLORS),
        textinfo="value+percent initial",
        textfont=dict(family=FONT_BODY, size=14),
        connector=dict(line=dict(color=BORDER)),
    ))
    funnel_layout = {k: v for k, v in PLOTLY_LAYOUT.items() if k != "margin"}
    fig_funnel.update_layout(**funnel_layout, height=240,
                             margin=dict(l=20, r=20, t=10, b=20))
    st.plotly_chart(fig_funnel, use_container_width=True, key="funnel_chart")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page: Pre-Annotation Coverage
# ---------------------------------------------------------------------------

elif page == "Pre-Annotation Coverage":
    st.header("Pre-Annotation Coverage")

    total = len(traces)
    t1 = sum(1 for r in tier1_results if r.auto_labeled)
    t2 = sum(1 for r in tier2_results if r.routed_to == "auto")
    eq = len(expert_results)

    st.markdown(page_intro_html(
        f"The three-tier system achieves <strong>{(t1+t2)/total*100:.0f}%</strong> "
        f"auto-annotation coverage, with only <strong>{eq/total*100:.0f}%</strong> "
        f"requiring expert review."
    ), unsafe_allow_html=True)

    # Metric cards with accent bars
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(metric_card_html("Tier 1 (Rules)", f"{t1} traces",
                    accent_color=TEAL_PRIMARY,
                    delta=f"{t1/total*100:.0f}% of total"), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card_html("Tier 2 (ML)", f"{t2} traces",
                    accent_color=SAGE,
                    delta=f"{t2/total*100:.0f}% of total"), unsafe_allow_html=True)
    with col3:
        st.markdown(metric_card_html("Expert Queue", f"{eq} traces",
                    accent_color=AMBER,
                    delta=f"{eq/total*100:.0f}% of total"), unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Stacked bar in section card
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Tier 1 (Rules)", x=["Coverage"], y=[t1],
        marker_color=TEAL_PRIMARY, text=[t1], textposition="inside",
        textfont=dict(color="white", size=14),
    ))
    fig.add_trace(go.Bar(
        name="Tier 2 (ML)", x=["Coverage"], y=[t2],
        marker_color=SAGE, text=[t2], textposition="inside",
        textfont=dict(color=TEAL_DARK, size=14),
    ))
    fig.add_trace(go.Bar(
        name="Expert Queue", x=["Coverage"], y=[eq],
        marker_color=AMBER, text=[eq], textposition="inside",
        textfont=dict(color="white", size=14),
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT, barmode="stack", height=280,
        title=dict(text="Coverage Stack", font=dict(
            family=FONT_HEADING, size=16, color=TEAL_DARK)),
        yaxis_title="Traces", xaxis=dict(showticklabels=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.05,
                    font=dict(family=FONT_BODY, size=12)),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Breakdown by ground truth label x tier
    rows = []
    for r in tier1_results:
        if r.auto_labeled:
            rows.append({"Ground Truth": r.ground_truth, "Tier": "Tier 1", "Label": r.label})
    for r in tier2_results:
        if r.routed_to == "auto":
            rows.append({"Ground Truth": r.ground_truth, "Tier": "Tier 2", "Label": r.predicted_label})
    for r in expert_results:
        rows.append({"Ground Truth": r.ground_truth, "Tier": "Expert", "Label": r.expert_label})

    if rows:
        breakdown = pd.DataFrame(rows)
        ct = pd.crosstab(breakdown["Ground Truth"], breakdown["Tier"])
        tier_order = ["Tier 1", "Tier 2", "Expert"]

        fig_bt = go.Figure()
        for tier, color in zip(tier_order, TIER_COLORS):
            if tier in ct.columns:
                fig_bt.add_trace(go.Bar(
                    name=tier, x=ct.index, y=ct[tier],
                    marker_color=color,
                ))
        fig_bt.update_layout(
            **PLOTLY_LAYOUT, barmode="group", height=350,
            title=dict(text="Breakdown by Pattern Type", font=dict(
                family=FONT_HEADING, size=16, color=TEAL_DARK)),
            yaxis_title="Traces", xaxis_title="Ground Truth Label",
            legend=dict(orientation="h", yanchor="bottom", y=1.05,
                        font=dict(family=FONT_BODY, size=12)),
        )
        st.plotly_chart(fig_bt, use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Rule Discovery
# ---------------------------------------------------------------------------

elif page == "Rule Discovery":
    st.header("Discovered Rules")

    # Split by source
    tree_rules = [r for r in candidate_rules if r.source == "decision_tree"]
    apriori_rules = [r for r in candidate_rules if r.source == "apriori"]

    st.markdown(page_intro_html(
        f"Pattern mining discovered <strong>{len(candidate_rules)}</strong> candidate rules "
        f"from decision tree splitting ({len(tree_rules)} rules) and Apriori association mining "
        f"({len(apriori_rules)} rules). These rules explain how features map to clinical labels."
    ), unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(metric_card_html("Decision Tree Rules", str(len(tree_rules)),
                    accent_color=TEAL_PRIMARY), unsafe_allow_html=True)
    with col2:
        st.markdown(metric_card_html("Apriori Rules", str(len(apriori_rules)),
                    accent_color=SAGE), unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    if candidate_rules:
        rules_df = pd.DataFrame([
            {
                "ID": r.rule_id,
                "Source": r.source,
                "Description": r.description,
                "Confidence": round(r.confidence, 3),
                "Support": round(r.support, 3),
            }
            for r in candidate_rules[:30]
        ])
        st.dataframe(rules_df, use_container_width=True, hide_index=True)

    # Feature importance from decision tree
    if tree is not None:
        st.subheader("Decision Tree Feature Importance")
        importances = tree.feature_importances_
        feat_imp = pd.DataFrame({
            "Feature": FEATURE_COLS,
            "Importance": importances,
        }).sort_values("Importance", ascending=True)
        feat_imp = feat_imp[feat_imp["Importance"] > 0]

        if not feat_imp.empty:
            fig = go.Figure(go.Bar(
                x=feat_imp["Importance"],
                y=feat_imp["Feature"],
                orientation="h",
                marker_color=TEAL_PRIMARY,
            ))
            fig.update_layout(
                **PLOTLY_LAYOUT,
                height=max(280, len(feat_imp) * 35),
                xaxis=dict(title="Importance", gridcolor=BORDER),
            )
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Page: Eval Scores
# ---------------------------------------------------------------------------

elif page == "Eval Scores":
    st.header("LLM Evaluator Scores")

    eval_results = _run_evals_mock(traces, final_labels, handoffs_map, seed=int(seed))

    eval_df = pd.DataFrame([
        {"Evaluator": r.evaluator, "Answer": r.answer, "Source": r.source}
        for r in eval_results
    ])

    if not eval_df.empty:
        # Pass rates per evaluator
        pass_rates = eval_df.groupby("Evaluator")["Answer"].apply(
            lambda x: (x == "Pass").mean() * 100
        ).reset_index()
        pass_rates.columns = ["Evaluator", "Pass Rate (%)"]

        overall_pass = eval_df["Answer"].eq("Pass").mean() * 100
        st.markdown(page_intro_html(
            f"Three LLM-as-judge evaluators assessed <strong>{len(eval_results)}</strong> "
            f"results across clinical accuracy, handoff quality, and artifact handling. "
            f"Overall pass rate: <strong>{overall_pass:.1f}%</strong>. "
            f"<em>Mock mode — switch to live for real Claude judgments.</em>"
        ), unsafe_allow_html=True)

        # Metric cards with accent bars
        pretty_names = {
            "artifact_handling": "Artifact Handling",
            "clinical_accuracy": "Clinical Accuracy",
            "handoff_quality": "Handoff Quality",
        }
        col1, col2, col3 = st.columns(3)
        for i, (_, row) in enumerate(pass_rates.iterrows()):
            col = [col1, col2, col3][i]
            name = pretty_names.get(row["Evaluator"], row["Evaluator"])
            pct = row["Pass Rate (%)"]
            color = EVAL_COLORS[i % len(EVAL_COLORS)]
            with col:
                st.markdown(metric_card_html(name, f"{pct:.1f}%",
                            accent_color=color,
                            delta=f"{int(eval_df[eval_df['Evaluator']==row['Evaluator']].shape[0])} evaluations"),
                            unsafe_allow_html=True)

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Gauge-style bar chart
        fig = go.Figure()
        for i, (_, row) in enumerate(pass_rates.iterrows()):
            name = pretty_names.get(row["Evaluator"], row["Evaluator"])
            fig.add_trace(go.Bar(
                x=[row["Pass Rate (%)"]], y=[name],
                orientation="h", name=name,
                marker_color=EVAL_COLORS[i % len(EVAL_COLORS)],
                text=[f"{row['Pass Rate (%)']:.1f}%"],
                textposition="auto",
                textfont=dict(color="white", size=14, family=FONT_BODY),
            ))
        fig.update_layout(
            **PLOTLY_LAYOUT, height=220,
            title=dict(text="Pass Rates by Evaluator", font=dict(
                family=FONT_HEADING, size=16, color=TEAL_DARK)),
            xaxis=dict(range=[0, 105], title="", gridcolor=BORDER,
                       showline=False, zeroline=False),
            showlegend=False,
            yaxis=dict(autorange="reversed", showgrid=False),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Detailed results
        with st.expander("Detailed Results", expanded=False):
            st.dataframe(eval_df.head(50), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page: Sample Handoffs
# ---------------------------------------------------------------------------

elif page == "Sample Handoffs":
    st.header("Sample Nurse Handoffs")

    st.markdown(page_intro_html(
        "Each trace generates a structured handoff summary for clinical staff, "
        "including urgency level, key findings, and patient context. "
        "Select a pattern type to see how the pipeline handles different clinical scenarios."
    ), unsafe_allow_html=True)

    # Pick sample traces (one per label)
    label_samples = {}
    for trace in traces:
        gt = trace.ground_truth_label
        if gt not in label_samples:
            label_samples[gt] = trace

    selected_label = st.selectbox(
        "Select pattern type",
        list(label_samples.keys()),
    )
    trace = label_samples[selected_label]

    # Show trace plot
    fig = plot_trace(trace, show_accel=True)
    st.plotly_chart(fig, use_container_width=True)

    # Show handoff
    final_label = final_labels.get(trace.night_id, trace.ground_truth_label)
    source = final_sources.get(trace.night_id, "unknown")

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Pipeline Handoff")
        handoff = handoffs_map.get(trace.night_id)
        if handoff:
            st.markdown(urgency_badge_html(handoff.urgency_level), unsafe_allow_html=True)
            st.write("")
            st.write(handoff.summary_text)
            st.caption(f"Source: {handoff.source} | Triage: {final_label} via {source}")

    with col2:
        st.subheader("Patient Details")
        details = {
            "Baby ID": trace.baby.baby_id,
            "GA": f"{trace.baby.gestational_age_weeks}w ({trace.baby.ga_category})",
            "Birth weight": f"{trace.baby.birth_weight_grams}g",
            "Days since birth": trace.baby.days_since_birth,
            "Conditions": ", ".join(trace.baby.known_conditions) or "None",
            "Ground truth": trace.ground_truth_label,
            "Pipeline label": final_label,
            "Mean SpO2": f"{np.mean(trace.spo2):.1f}%",
            "Min SpO2": f"{np.min(trace.spo2):.0f}%",
            "Events": len(trace.events),
        }
        for k, v in details.items():
            st.markdown(detail_row_html(k, str(v)), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page: Run Single Trace
# ---------------------------------------------------------------------------

elif page == "Run Single Trace":
    st.header("Interactive Single-Trace Demo")

    st.markdown(page_intro_html(
        "Generate a synthetic overnight SpO2 trace with custom parameters, "
        "run it through the rule engine, and see the classification, handoff, "
        "and evaluator results in real time."
    ), unsafe_allow_html=True)

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        ga = st.slider("Gestational age (weeks)", 24, 42, 34)
    with col2:
        pattern = st.selectbox("Pattern type", ["normal", "urgent", "borderline", "artifact"])
    with col3:
        trace_seed = st.number_input("Trace seed", value=123)

    if st.button("Generate & Analyze", type="primary"):
        rng = np.random.default_rng(int(trace_seed))
        babies = generate_baby_cohort(1, rng)
        baby = babies[0]
        # Override GA
        from src.data_gen.synthetic import _classify_ga
        baby.gestational_age_weeks = ga
        baby.ga_category = _classify_ga(ga)

        trace = generate_trace(baby, pattern, 1, rng)

        # Show trace
        fig = plot_trace(trace, show_accel=True)
        st.plotly_chart(fig, use_container_width=True)

        # Run rules
        rule_result = apply_rules(trace)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("Tier 1 (Rules)")
            if rule_result.auto_labeled:
                st.success(f"Label: **{rule_result.label}**")
                st.write(f"Rule: {rule_result.rule_triggered}")
                st.write(f"Confidence: {rule_result.confidence}")
            else:
                st.warning("No rule matched — routes to Tier 2")

        with col2:
            st.subheader("Classification")
            final_label = rule_result.label or pattern  # fallback
            st.write(f"**Final label:** {final_label}")
            st.write(f"**Ground truth:** {pattern}")
            if final_label == pattern:
                st.success("Correct!")
            else:
                st.error(f"Mismatch: predicted {final_label}, actual {pattern}")

        with col3:
            st.subheader("Handoff")
            handoff = generate_handoff(trace, final_label, use_llm=False)
            st.markdown(urgency_badge_html(handoff.urgency_level), unsafe_allow_html=True)
            st.write("")
            st.write(handoff.summary_text)

        # Eval results
        st.subheader("Evaluator Results")
        s = int(trace_seed)
        evals = [
            evaluate_clinical_accuracy(trace, final_label, seed=s),
            evaluate_handoff_quality(trace, handoff, final_label, seed=s+1),
            evaluate_artifact_handling(trace, final_label, seed=s+2),
        ]
        eval_df = pd.DataFrame([
            {"Evaluator": e.evaluator.replace("_", " ").title(),
             "Result": e.answer, "Reasoning": e.reasoning}
            for e in evals
        ])
        st.dataframe(eval_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page: Design System
# ---------------------------------------------------------------------------

elif page == "Design System":
    st.header("Design System")
    st.caption("Owlet-inspired tokens — colors, typography, and component patterns")

    # --- Color Palette ---
    st.subheader("Color Palette")

    def _swatch(hex_color: str, name: str, usage: str) -> str:
        """Render an HTML color swatch card."""
        # Use white text on dark colors, dark text on light
        text_color = "#FEFCFA" if hex_color in (TEAL_DARK, URGENT_RED, AMBER, NEUTRAL_GRAY) else TEAL_DARK
        return (
            f'<div style="display:inline-block; width:155px; margin:0 10px 12px 0; '
            f'border-radius:12px; overflow:hidden; border:1px solid {BORDER}; '
            f'background:{WARM_WHITE}; vertical-align:top;">'
            f'<div style="background:{hex_color}; height:56px; display:flex; '
            f'align-items:flex-end; padding:6px 10px;">'
            f'<span style="font-size:0.7rem; font-weight:600; color:{text_color}; '
            f'background:rgba(255,255,255,0.15); padding:1px 6px; border-radius:3px;">'
            f'{hex_color}</span></div>'
            f'<div style="padding:8px 10px;">'
            f'<div style="font-weight:600; color:{TEAL_DARK}; font-size:0.82rem;">{name}</div>'
            f'<div style="color:{MUTED_TEXT}; font-size:0.72rem; margin-top:1px;">{usage}</div>'
            f'</div></div>'
        )

    st.markdown("**Primary / Brand**", unsafe_allow_html=True)
    swatches = (
        _swatch(TEAL_DARK, "Teal Dark", "Headings, dark text")
        + _swatch(TEAL_PRIMARY, "Teal Primary", "Buttons, accents, links")
        + _swatch(TEAL_LIGHT, "Teal Light", "Icons, secondary labels")
        + _swatch(SAGE, "Sage", "Secondary chart bars")
    )
    st.markdown(swatches, unsafe_allow_html=True)

    st.markdown("**Backgrounds & Surfaces**", unsafe_allow_html=True)
    swatches = (
        _swatch(CREAM_BG, "Cream BG", "Page background")
        + _swatch(WARM_WHITE, "Warm White", "Cards, sidebar, plots")
        + _swatch(SAGE_BG, "Sage BG", "Table headers, highlights")
        + _swatch(BORDER, "Border", "Dividers, grid lines")
    )
    st.markdown(swatches, unsafe_allow_html=True)

    st.markdown("**Clinical Status**", unsafe_allow_html=True)
    swatches = (
        _swatch(URGENT_RED, "Urgent Red", "SpO2 < 90%")
        + _swatch(AMBER, "Amber", "Borderline, 90-94%")
        + _swatch(NEUTRAL_GRAY, "Neutral Gray", "Artifact, disabled")
    )
    st.markdown(swatches, unsafe_allow_html=True)

    # --- Typography ---
    st.subheader("Typography")

    type_samples = [
        (f"font-family:{FONT_HEADING}; color:{TEAL_DARK}; font-weight:600; font-size:2rem;",
         "Neonatal SpO2 AI Eval Pipeline",
         f"H1 — Playfair Display 600 / 2rem"),
        (f"font-family:{FONT_HEADING}; color:{TEAL_DARK}; font-weight:500; font-size:1.4rem;",
         "Pipeline Overview",
         "H2 — Playfair Display 500 / 1.4rem"),
        (f"font-family:{FONT_HEADING}; color:{TEAL_DARK}; font-weight:500; font-size:1.15rem; font-style:italic;",
         "monitor what matters most",
         "H3 Italic — Playfair Display 500 italic / 1.15rem"),
        (f"font-family:{FONT_BODY}; color:{BODY_TEXT}; font-size:0.95rem; line-height:1.5;",
         "The pipeline generates synthetic pulse oximetry data with gestational-age-adjusted baselines.",
         f"Body — DM Sans 400 / 0.95rem"),
        (f"font-family:{FONT_BODY}; color:{MUTED_TEXT}; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.06em;",
         "TOTAL TRACES",
         "Label — DM Sans / 0.78rem / uppercase"),
    ]

    for style, text, meta in type_samples:
        st.markdown(
            f'<div style="background:{WARM_WHITE}; border:1px solid {BORDER}; '
            f'border-radius:12px; padding:18px 22px; margin-bottom:10px;">'
            f'<div style="{style}">{text}</div>'
            f'<div style="color:{MUTED_TEXT}; font-size:0.72rem; margin-top:6px; '
            f'font-family:{FONT_BODY};">{meta}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # --- Component Patterns ---
    st.subheader("Component Patterns")

    # Metric cards
    st.markdown("**Metric Cards**")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Traces", "300")
    mc2.metric("Tier 1 (Rules)", "183 (61%)")
    mc3.metric("Clinical Accuracy", "89.2%")

    # Urgency badges
    st.markdown("**Urgency Badges**")
    badges = "".join(urgency_badge_html(level) + "&nbsp;&nbsp;" for level in URGENCY_COLORS)
    st.markdown(badges, unsafe_allow_html=True)
    st.write("")

    # Chart color sequences
    st.markdown("**Chart Color Sequences**")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("*Tier sequence*")
        dots = ""
        for name, color in [("Tier 1", TEAL_PRIMARY), ("Tier 2", SAGE), ("Expert", AMBER)]:
            dots += (
                f'<span style="display:inline-flex; align-items:center; margin-right:16px;">'
                f'<span style="width:18px; height:18px; border-radius:50%; '
                f'background:{color}; display:inline-block; margin-right:6px;"></span>'
                f'<span style="font-size:0.85rem; color:{BODY_TEXT};">{name}</span></span>'
            )
        st.markdown(dots, unsafe_allow_html=True)

    with col2:
        st.markdown("*Clinical labels*")
        dots = ""
        for name, color in LABEL_COLORS.items():
            dots += (
                f'<span style="display:inline-flex; align-items:center; margin-right:16px;">'
                f'<span style="width:18px; height:18px; border-radius:50%; '
                f'background:{color}; display:inline-block; margin-right:6px;"></span>'
                f'<span style="font-size:0.85rem; color:{BODY_TEXT};">{name}</span></span>'
            )
        st.markdown(dots, unsafe_allow_html=True)

    # Patient detail rows
    st.write("")
    st.markdown("**Patient Detail Row**")
    st.markdown(detail_row_html("Gestational Age", "32w (very preterm)"), unsafe_allow_html=True)
    st.markdown(detail_row_html("Mean SpO2", "94.2%"), unsafe_allow_html=True)
    st.markdown(detail_row_html("Pipeline Label", "borderline"), unsafe_allow_html=True)
