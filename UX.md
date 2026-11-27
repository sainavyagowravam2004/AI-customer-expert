# Task 0: Screen Map, Navigation & Wireframes

## 1. End-to-End Screen Flow
Sign Up / Demo Login (/login) -> Go Live in 15 Mins (/go-live, Readiness Score >= 80) -> Settings & Roles (/settings) | Knowledge Brain (/knowledge: Sitemaps, Page URLs, Instructions, Skills, Past Emails) | Ask & Teach Chat (/chat: Ask Something, Teach Me) | Email Inbox (/inbox) | Eval Lab & Self-Improve (/evals).

## 2. Screen & Tab Inventory
| Screen | Route | Internal Tabs / Modes | What It Shows & Where Actions Lead |
| :--- | :--- | :--- | :--- |
| Auth | /login | Sign In, Create Workspace, Demo Login | Authenticates user, sets HTTP-only cookie, routes to /settings or /go-live. |
| Go Live (15m) | /go-live | Guided Setup Wizard | Ingests sitemap/FAQ, generates starting tests, computes Readiness Score (0-100). |
| Settings | /settings | Workspace, 5 Connections, Agent Roles, Logs | Saves Fernet-encrypted keys, tests connections, creates/tests Agent Roles. |
| Knowledge Brain | /knowledge | Sitemaps, Page URLs, Instructions, Skills, Past Emails | Previews sitemaps, crawls pages, sets URL health (Active/Watch/Quarantined/Archived), tests hybrid RRF search. |
| Ask & Teach Chat | /chat | Ask Something, Teach Me | Answers with citations & cost trace; saves corrections to lessons/*.md; escalates refund/legal/angry queries. |
| Email Inbox | /inbox | Pending Review, Resolved Threads | Simulates inbound email, generates AI draft, captures human edits as approved lessons. |
| Eval Lab | /evals | Side-by-Side Benchmark, Self-Improve Runs | Compares 14 models (including Local-Only Switch), proposes & approves patches. |

## 3. Wireframes
- Knowledge Brain (/knowledge): Top KPI cards (Pages, Hybrid Chunks, Rules & Skills) -> 5 horizontal tabs (1. Sitemaps, 2. Page URLs, 3. Instructions, 4. Skills, 5. Past Emails) -> Sitemap Pre-Crawl Summary & Confirm button -> Hybrid Search Tester.
- Ask & Teach Chat (/chat): Header with Ask Something vs Teach Me toggle + Role selector -> Message stream with source citations, model/cost trace, and Teach/Flag inline correction box -> Input bar.
