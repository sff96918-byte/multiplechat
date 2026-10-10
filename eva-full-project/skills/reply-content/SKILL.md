---
name: reply-content
description: bot-এর reply বদলানো, নতুন line যোগ করা, trigger keyword বাড়ানো, বা funnel কোন step-এ কোন ফাইল থেকে reply আসে বোঝার জন্য এটা পড়ো। Reply content কোড না বদলে txt দিয়েই করা হয়।
---

# SKILL: Reply content (txt-ভিত্তিক, কোড ছাড়া)

## মূল নিয়ম
```
data/input/<name>.txt   = ইউজার কী লিখল (trigger keyword/phrase)
data/output/<name>.txt  = bot কী লিখবে (reply লাইন, একটা লাইন = একটা reply)
একই নাম = একই category
```
Editable — বদলালে restart লাগে (process নতুন করে চালু)।

## Funnel (ডিফল্ট flow engine)
```
first SMS (hi)        → greeting.txt
age/gender (m21)      → age_gender.txt   → এরপর country প্রশ্ন
country (usa)         → country.txt → flirty_questions.txt → MIDDLE
horny (u horny?)      → horny.txt → MIDDLE
flirt (ur cute)       → middle_chat/flirty_reply.txt
lol/ok/nice           → middle_chat/warm_reply.txt
gtg/bye/brb           → middle_chat/busy_later.txt
how are u / age       → how_are_you.txt / your_age.txt
positive (yes / ur sc?) → share_snap.txt → END CHAT
snap দেয় (my snap is…) → snapchat.txt → END CHAT
অন্য কিছু            → flirty_questions.txt
৮টা bot reply-র পরে  → closer.txt → END CHAT
```
Matching layer (একটা fail হলে পরেরটা): exact → substring → slang-normalize →
token-subset → regex fallback (countries.txt)।

পূর্ণ বাংলা guide: `data/output/info.txt`; English: `README.md`।

## কাজের ধাপ
1. নতুন reply লাইন চাইলে → সঠিক `output/*.txt`-এ এক লাইন যোগ (duplicate এড়াও)।
2. নতুন trigger চাইলে → সঠিক `input/*.txt`-এ এক লাইন।
3. Engine-এর চেয়ে content বদল আগে — কোড বদল শেষ অপশন।
4. যাচাই: `python tools/live_chat.py` (নিজে stranger হয়ে টাইপ) — প্রতিটা reply-র নিচে কোন file:line থেকে এসেছে দেখায়।
5. `python test_matcher.py` (pool round-trip) ও `python test_live.py`।

## সতর্কতা
- কোনো file-এ ফাঁকা লাইন/ডুপ্লিকেট যোগ করো না; UTF-8 সেভ করো।
- `{snap}` placeholder `_resolve_snap_reply()` দিয়ে resolve হয় — হাতে বসাবে না।
- Funnel state-এর নাম বদলালে `eva_flow.py` ও `docs/FLOW_SPEC.md` একসাথে আপডেট।
- Adult/explicit content: বর্তমান content filter (`chat/content_filter.py`) ও horny রুট
  বদলাবে না — সেটা ইউজারের সিদ্ধান্ত।
