"""Render a private v5 sample without committing personal resume data."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.materials.pdf_renderer import render_tailored_resume
from src.materials.template import ResumeTemplate, TailoredResumeSections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = render_tailored_resume(
        args.source,
        args.output,
        TailoredResumeSections(
            professional_summary=(
                "Chief AI Architect with nearly 10 years of experience "
                "leading enterprise LLM platforms, agent delivery, and "
                "cross-functional AI transformation in large organizations."
            ),
            career_highlights=(
                "Enterprise LLM Platform - Unified secure model services and "
                "production agent capabilities at scale.",
                "Matrix Leadership - Led a core AI team and governed delivery "
                "across departmental engineering teams.",
                "Business Impact - Converted enterprise AI architecture into "
                "measurable operational and commercial outcomes.",
                "AI Governance - Deployed production guardrails, architecture "
                "reviews, and vendor strategy.",
            ),
            core_competencies=(
                "Enterprise AI Leadership - Direct and matrix leadership",
                "LLM and Agent Platforms - RAG, LLMOps and optimization",
                "Architecture Governance - Security and technical approval",
            ),
        ),
        ResumeTemplate.v5(),
    )
    if result.overflow:
        raise SystemExit(f"render failed: {result.overflow}")
    print(args.output)


if __name__ == "__main__":
    main()
