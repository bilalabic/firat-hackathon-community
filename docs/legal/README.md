# Legal notes (not legal advice)

## KVKK cross-border transfer (KVKK m. 9, amended by Law No. 7499, in force since 2024-06-01)

Applicant data is **stored continuously** with Supabase (EU, Frankfurt) and processed through
Vercel (a US company; functions run in fra1). First names also reach Telegram for admin
notifications. These are regular, not occasional, transfers abroad.

Since the 2024 amendment, the order of legal bases is:

1. an **adequacy decision** by the Board;
2. **appropriate safeguards**, e.g. the Board's **standard contract** signed with the recipient and
   notified to the Authority within **5 business days** of signature, or binding corporate rules;
3. only for **occasional (arızi)** transfers: explicit consent and the other exceptions.

Explicit consent is therefore not a sound basis for this processing.

Options for the owner (decide before the forms go live):

| Option | Effect |
|---|---|
| A. Get legal advice and put the matching safeguard in place (standard contract and notification) | Correct, but slower; providers may not sign the Board's template |
| B. Keep the site live and the **forms closed** until A is done | The event directory works now; nothing personal is collected |
| C. Collect the minimum in the forms (e.g. only name + channel handle) | Reduces exposure, does not remove the transfer question |

Sources (secondary, by Turkish law firms; checked 2026-10-06):

- [Erdem & Erdem](https://www.erdem-erdem.av.tr/bilgi-bankasi/kisisel-verilerin-korunmasi-kanununda-neler-degisti)
- [Arifoğlu & Aydın](https://arifogluaydin.com/bulten/kvkk-acik-riza-ile-yurt-disi-aktarimi)
- [GSG Hukuk](https://www.gsghukuk.com/tr/bultenler-yayinlar/duyurular/kisisel-verilerin-yurt-disina-aktarilmasina-iliskin-usul-ve-esaslar-hakkinda-yonetmelik-yururluge-girdi.html)

The primary source is the law text in the Resmî Gazete.

## Retention (owner decision 2026-10-06)

12 months after the last action on an application, then delete or anonymise. **Not automated
yet.** A scheduled deletion job is a follow-up item.
