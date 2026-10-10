# USER PREFERENCES (কীভাবে কাজ করতে হবে)

## ভাষা ও tone
- ইউজার বাংলা/Banglish-এ লেখেন। Reply বাংলায় দাও (technical শব্দ ইংরেজিতেই থাক)।
- স্বাগত জানানো হয় "ভাই" সম্বোধনে; ইউজার মাঝে মাঝে "sir" বলেন — friendly-professional থাকো।

## কাজের ধরন
- **Evidence-based কাজ** — capture/প্রমাণ ছাড়া কিছু guess করা যাবে না (প্রজেক্টের HARD RULE)।
- ইউজার "deeply analyze", "step by step" শব্দগুলো বললে সত্যিই পুরোটা গলা ধরে চেক করো — surface fix নয়।
- কাজ শেষে: কী কী bug পাওয়া গেল, কী কী fix হলো, test results — টেবিল করে বাংলায় সাজাও।
- বড় কাজে নিজে থেকে test suite বাড়াও (naya scenario = naya check)।

## Delivery
- চূড়ান্ত ডেলিভারি সবসময় **zip** বানিয়ে দাও + **GitHub direct download link** (raw) + exact byte size (verify করে)।
- ইউজার PC থেকে কাজ করেন (Windows) — .bat/.vbs launcher রাখো, বাংলা guide (BANGLA_QUICK_START.txt) আপডেট রাখো।
- secrets (session.json/cookies) কখনো zip বা git-এ যাবে না — zip বানানোর পর verify করো।

## পছন্দ
- Desktop **EXE dashboard** চান (web dashboard শুধু alternative) — PyQt6 dark professional style (তার পুরনো প্রজেক্টের মতো)।
- Reply engine = তার পুরনো txt-bank funnel (flow) — এটাই default।
- ইউজার এক task-এ এক agent-কে কাজ দেন, পরের task প্রায়ই নতুন session-এ → memory system সবসময় আপডেট রাখো।

## যোগাযোগ
- সমস্যা হলে ইউজার console output/screenshot পাঠাবে বলে বলা হয়।
- সমস্যা বুঝতে না পারলে ask_user tool দিয়ে clear option দাও।
