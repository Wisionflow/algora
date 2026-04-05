---
name: algora-strategy
description: |
  Skill for Algora's strategic planning and market analysis — segment scoring, hypothesis evaluation, audience-platform strategy, and decision-making frameworks. Use this skill whenever the task involves: evaluating new market segments or business hypotheses, updating the segment scoring matrix (30+ hypotheses across 4 capital types), planning audience growth strategy, deciding which segment to target next, analyzing cross-border market opportunities, working with the four-layer capital architecture (Human → Commodity → Financial → Political), budgeting and KPI planning, competitive analysis for Telegram channels serving sellers/importers, or any strategic decision about Algora's direction. Also trigger when someone asks about the two-level value model (Product level vs Platform level), the three AI agents architecture (Growth → Market Analyst → Product Discovery), or how to evaluate market fit. If the user mentions manifesto, strategic plan, segment scoring, market analysis, or asks "what should we do next" — use this skill.
---

# Algora Strategy

## Core Model

Algora operates a **two-level value model**:

- **Level 1 (Product):** For each audience segment → create an AI product (content channel, bot, SaaS). This attracts and retains the audience, covers growth costs, generates revenue.
- **Level 2 (Platform):** When critical mass is reached across segments → connect audiences on a platform where one group's need is solved by another. This is the main profit center.

## Three Phases

```
Phase 1: Audience Engine → grow one segment + monetize with AI product
Phase 2: Replication → copy the model to adjacent segments (chosen by data)
Phase 3: Platform → connect audiences for mutual value exchange
```

## Current Segment: T1

**T1: Chinese factories → WB/Ozon sellers (Score: 70/85)**

Why T1 won:
- Pain 5/5 — sellers lose money daily on bad product choices
- Fact-density 5/5 — pure data (prices, margins, trends), perfect for AI
- Audience 5/5 — 300K-500K active sellers on WB/Ozon
- Clear AI product potential — content channel → bot → SaaS dashboard

Next candidates (to be validated after Growth Agent proves the model):
- **H6** — International trade lawyers (score 69, highest cross-segment connectivity 5/5)
- **T2** — Auto parts sourcing (score 67, acute post-sanctions need)
- **T5** — Industrial equipment import substitution (score 67)

## Segment Scoring Methodology

### 7 Criteria (v1.0)

| Criterion | Weight | What It Measures |
|-----------|--------|-----------------|
| Pain severity | x3 | Does the audience lose money/time without a solution? |
| Fact-density | x3 | Can AI solve this with data (not emotions/creativity)? |
| Source availability | x3 | Are there open data sources AI can parse? |
| Audience size | x2 | Enough people for critical mass? |
| Willingness to pay | x2 | Does this audience already pay for tools? |
| Cross-segment connectivity | x2 | Natural "pair" segment for Level 2? |
| Competition (inverted) | x1 | Less competition = higher score |

**Max score: 85** (5×3 + 5×3 + 5×3 + 5×2 + 5×2 + 5×2 + 5×1)

### v2.0 Additions (pending re-scoring)

New criterion: **AI-product potential** (x3) — Does the audience have repeatable tasks AI can automate and monetize?

This changes max score and requires re-evaluation of all 30 hypotheses.

## Four Layers of Capital

```
┌─────────────────────────────────────┐
│  🏛  Political Capital (GR)        │  ← Tier 4: permissions, scale
├─────────────────────────────────────┤
│  💰 Financial Capital              │  ← Tier 3: money
├─────────────────────────────────────┤
│  📦 Commodity Capital              │  ← Tier 2: trade (WE ARE HERE — T1)
├─────────────────────────────────────┤
│  👥 Human Capital                  │  ← Tier 1: expertise
└─────────────────────────────────────┘
```

Strategy: start at Commodity (T1), expand horizontally, then move up layers.

## 40 Hypotheses Overview

Organized by capital type:
- **T1-T10:** Commodity (Production ↔ Retail) — factories, suppliers, sellers
- **F1-F10:** Financial (Investors ↔ Projects) — angels, funds, crowdlending
- **H1-H10:** Human (Experts ↔ Business) — outsourcing, lawyers, medtourism
- **P1-P10:** Political (Government ↔ Business) — OEZ, grants, trade reps

Full scoring table in SEGMENT_SCORING.md. Top 5:
1. T1: Electronics → MP sellers (70)
2. H6: Lawyers → Exporters (69)
3. T2: Auto parts → Service centers (67)
4. T5: Equipment → Import substitution factories (67)
5. T7: Construction materials → Developers (66)

## Three AI Agents

| Agent | Purpose | When |
|-------|---------|------|
| **Growth Agent** | Autonomously acquire audience | NOW (Priority #1) |
| **Market Analyst** | Monitor market, choose next segments | Parallel with Growth |
| **Product Discovery** | Monitor audience needs, propose AI products | After 200-500 subscribers |

## Decision Framework: "What Should We Do Next?"

When evaluating any strategic decision, apply this checklist:

1. **Does it help reach 100 subscribers?** If no → defer it.
2. **Is it automated or manual?** Manual work = architectural dead end.
3. **Does it generate data?** Decisions should be data-driven, not intuitive.
4. **Does it compound?** Prefer investments that grow over time (content, audience, tools).
5. **What's the cost of delay?** Some things (like VK) can safely wait.

## What NOT To Do

- Don't monetize before 500 subscribers
- Don't choose next segment by intuition (wait for Market Analyst data)
- Don't spend time on VK (focus on Telegram)
- Don't buy ads before 100+ organic subscribers
- Don't add new data sources (Pinduoduo, Taobao) — current pipeline works
- Don't build AI products without Product Discovery Agent validation

## Budget Framework

| Phase | Monthly Spend | Focus |
|-------|--------------|-------|
| Current (0-100 subs) | $5-10 | API + Apify only |
| Growth (100-500 subs) | $35-70 | + small ad spend |
| Monetization (500+) | $130-300 | + scaled ads |
| Reserve | up to $500 | Emergency/opportunity |

## KPIs by Timeline

| When | Metric | Target |
|------|--------|--------|
| Week 1 | Growth Agent deployed | Container running, first responses |
| 2 weeks | Calibration complete | Agent answers relevantly in 10+ chats |
| 1 month | Proof of concept | 100+ subscribers via Growth Agent |
| 2 months | Stable growth | 300+ subscribers, conversion measured |
| 3 months | Ready for Level 1 | 500+ subs, Product Discovery launched |
| 6 months | Revenue | First income from AI product |

## Partnership Context

Algora is a partnership project (Mantas + Alexander):
- **Mantas** (us): Growth Agent, content pipeline, strategy
- **Alexander** (partner): Server infrastructure, Algora CEO/Portal/CSO/News
- **Protocol:** algora-sync GitHub repo, REQUEST/APPROVAL workflow
- **Our Claude = SUPPORT, Partner's Claude = LEAD** for server operations
