# ROADMAP.md — Planned Feature Ideas (Build Order & Dependencies)


## Build Priority Order

| Priority | Feature Name & Spec File | Core Value | Dependencies | Est. Hours |
| :--- | :--- | :--- | :--- | :--- |
| **1 (Build First)** | [Live Gmail Auto-Draft & Human Triage Queue](features/gmail-auto-draft-triage.md) | Eliminates manual copy-pasting by auto-generating role-matched Gmail drafts for incoming customer threads and routing angry/refund/legal emails to a human queue[cite: 9, 10]. | **None** (uses existing Feature 1 Gmail OAuth, Feature 2 Knowledge API, and Feature 3 Safety Guardrails)[cite: 5, 9, 10, 16]. | 10 hrs |
| **2 (Build Second)** | [Knowledge Gap Detector & Auto-Article Drafter](features/knowledge-gap-drafter.md) | Clusters unanswered ("I don't know") questions and repeated human corrections into prioritized missing-article reports with AI-drafted help center pages[cite: 9, 10]. | Requires **Feature #1** (or live chat volume) to accumulate real unanswered customer queries[cite: 16]. | 8 hrs |
| **3 (Build Third)** | [Embeddable Customer Self-Service Widget](features/embeddable-support-widget.md) | A lightweight `<script>` widget businesses embed on their own site so end-customers self-serve answers before creating a support ticket. | Requires **Feature #2** so common customer questions already have verified knowledge articles[cite: 16]. | 12 hrs |
| **4 (Build Fourth)** | [Multi-Language Auto-Translate & Locale Routing](features/multi-language-routing.md) | Detects incoming customer language, translates queries to match English help docs, and replies natively in the customer's language with locale-specific tone. | Requires **Features #1 & #3** (covers both Gmail and widget channels) and adds multi-lingual eval cases to Feature 4[cite: 16]. | 9 hrs |

## Why This Order?
1. **#1 First (Highest ROI, Lowest Friction):** Businesses already connect Gmail in Feature 1[cite: 5]. Turning passive email reading into active Gmail draft creation delivers immediate value with zero new external integrations[cite: 8, 16].
2. **#2 Second (Closes the Knowledge Loop):** Once real customer questions flow in through #1, clustering "I don't know" escalations shows the business owner exactly which help articles to write next[cite: 9, 10, 16].
3. **#3 Third (Deflects Tickets Upstream):** After the Knowledge Brain is strengthened by #2, exposing a read-only widget directly to end-users deflects up to 60% of repetitive tickets before they reach Gmail[cite: 16].
4. **#4 Fourth (Global Expansion):** Adding native multi-language support last ensures all core workflows (Gmail drafts, knowledge gap tracking, and the public widget) are already stable and evaluated before adding translation latency and cross-lingual eval complexity[cite: 16].
