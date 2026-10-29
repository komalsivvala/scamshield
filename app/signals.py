"""Deterministic, explainable fraud signals. They run before any model call, so the
verdict is grounded in checks that can be audited, and serve as a baseline in evals."""
import re
from urllib.parse import urlparse

URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"')\]]+"
    r"|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|in|net|org|xyz|top|info|co|io|link|click|buzz|icu|shop|site|"
    r"online|live|app|me|ly|gl|cc|vip|club|tk|ml|ga|cf|gq|pw|rest|sbs|cfd|bond|lat)(?:/[^\s<>\"')\]]*)?",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
UPI_RE = re.compile(
    r"\b[\w.\-]{2,}@(?:ok(?:sbi|hdfcbank|icici|axis)|ybl|ibl|axl|paytm|upi|apl|sbi|icici|hdfcbank|axisbank|kotak|"
    r"yesbank|fbl|jupiteraxis|freecharge|airtel|pthdfc|ptsbi|ptyes|ptaxis|waicici|wahdfcbank|indus|idfcbank|barodampay)\b",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s-]?)?(?:[6-9]\d{4}[\s-]?\d{5}|1800[\s-]?\d{3}[\s-]?\d{3,4}|\d{3}[\s-]\d{3}[\s-]\d{4})(?![\w])")

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.ly", "cutt.ly", "is.gd", "goo.gl", "rb.gy", "shorturl.at", "tiny.cc",
    "s.id", "rebrand.ly", "ow.ly", "t.co", "bitly.ws", "shorte.st", "v.gd", "qr.ae",
}
RISKY_TLDS = {
    "xyz", "top", "click", "buzz", "icu", "shop", "site", "online", "live", "vip", "club", "tk", "ml", "ga",
    "cf", "gq", "pw", "rest", "sbs", "cfd", "bond", "lat", "info",
}
OFFICIAL_DOMAINS = {
    "sbi": ["sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "sbicard.com"],
    "hdfc": ["hdfcbank.com", "hdfc.bank.in"],
    "icici": ["icicibank.com", "icici.bank.in"],
    "axis": ["axisbank.com", "axis.bank.in"],
    "kotak": ["kotak.com"],
    "paytm": ["paytm.com"],
    "phonepe": ["phonepe.com"],
    "amazon": ["amazon.in", "amazon.com"],
    "flipkart": ["flipkart.com"],
    "irctc": ["irctc.co.in"],
    "indiapost": ["indiapost.gov.in"],
    "incometax": ["incometax.gov.in"],
    "epfo": ["epfindia.gov.in"],
    "uidai": ["uidai.gov.in"],
    "aadhaar": ["uidai.gov.in"],
    "npci": ["npci.org.in"],
    "fedex": ["fedex.com"],
    "dhl": ["dhl.com"],
    "bluedart": ["bluedart.com"],
    "netflix": ["netflix.com"],
    "paypal": ["paypal.com"],
    "apple": ["apple.com"],
    "microsoft": ["microsoft.com"],
    "whatsapp": ["whatsapp.com"],
    "jio": ["jio.com"],
    "airtel": ["airtel.in"],
    "usps": ["usps.com"],
    "irs": ["irs.gov"],
}
BRAND_WORDS = re.compile(
    r"\b(sbi|state bank|hdfc|icici|axis bank|kotak|paytm|phonepe|google pay|gpay|amazon|flipkart|irctc|india post|"
    r"income tax|epfo|uidai|aadhaa?r|npci|rbi|reserve bank|fedex|dhl|blue ?dart|netflix|paypal|apple|microsoft|"
    r"whatsapp|jio|airtel|electricity (board|department|office)|electricity|bescom|tneb|msedcl|customs|police|cbi|trai|usps|irs)\b",
    re.IGNORECASE,
)

NEGATION = re.compile(r"(do not|don't|dont|never|not|no one|nobody|won't)\W+(?:\w+\W+){0,3}$", re.IGNORECASE)

# (id, severity, title, regex, explanation)
TEXT_RULES = [
    ("credential_request", "high", "Asks for OTP / PIN / password",
     r"\b(share|send|tell|provide|enter|confirm|forward|reply with)\b[^.\n]{0,40}\b(otp|pin|cvv|password|passcode|verification code)\b",
     "Banks, apps and government offices never ask you to share an OTP, PIN, CVV or password."),
    ("pin_to_receive", "high", "PIN needed to 'receive' money",
     r"(enter|use)[^.\n]{0,25}\bpin\b[^.\n]{0,30}\b(receive|get|credit|claim)\b|\b(receive|claim|get)\b[^.\n]{0,30}\b(enter|scan)[^.\n]{0,20}(pin|qr)",
     "You never need to enter a UPI PIN or scan a QR code to RECEIVE money. That only sends money out."),
    ("account_threat", "high", "Threatens to block your account / service",
     r"\b(account|card|sim|number|connection|kyc|wallet|service|pan)\b[^.\n]{0,40}\b(block|suspend|deactivat|disconnect|clos|freez|terminat|barred)",
     "Scammers create fear of losing access so you act without thinking."),
    ("power_cut", "high", "Electricity disconnection threat",
     r"(electricity|power|light)[^.\n]{0,40}(disconnect|cut|discontinu)|(disconnect|cut)[^.\n]{0,30}(electricity|power)",
     "The 'electricity will be cut tonight' message is one of the most common scams in India."),
    ("authority_threat", "high", "Police / CBI / customs / 'digital arrest' threat",
     r"digital arrest|\bcbi\b|narcotics|money laundering|arrest warrant|cyber ?cell|police (case|complaint)|customs (duty|department|officer)|illegal (items|drugs)|\bed\b officer|\btrai\b",
     "Real police or agencies never 'arrest' people over video calls or ask for money to close a case."),
    ("kyc_update", "medium", "KYC / PAN / Aadhaar update demand",
     r"\b(kyc|pan|aadhaa?r)\b[^.\n]{0,40}\b(update|verify|verification|link|expired|expire|pending|incomplete)"
     r"|\b(update|verify|complete|link)\b[^.\n]{0,20}\b(kyc|pan|aadhaa?r)\b",
     "KYC is updated at your branch or in the official app, never through a link in an SMS."),
    ("urgency", "medium", "Creates urgency / deadline pressure",
     r"\b(urgent|urgently|immediately|within \d+ ?(hours?|hrs|minutes?|mins)|today itself|tonight|last (chance|warning|reminder|date)|act now|final notice|expir(es|ing) today)\b",
     "Pressure to act fast is a classic manipulation tactic."),
    ("prize", "medium", "Prize / lottery / unexpected reward",
     r"\b(lottery|lucky draw|you (have )?won|winner|prize|jackpot|congratulations[^.\n]{0,40}(selected|won)|free gift|reward points?[^.\n]{0,25}(expir|redeem))",
     "Unexpected prizes that need a fee or your details are almost always scams."),
    ("job_task", "high", "Easy-money job / online tasks",
     r"part[- ]?time (job|work)|work from home[^.\n]{0,40}(earn|₹|rs)|daily (income|earning|salary)|earn (₹|rs\.?|inr)? ?\d[\d,]* ?(per day|daily|/day)|like (youtube )?videos|rate (hotels|products)|prepaid task|telegram (task|group)",
     "Task-based job scams pay small amounts first, then ask you to 'invest' larger sums."),
    ("investment", "high", "Guaranteed / unrealistic returns",
     r"guaranteed (returns?|profit)|double your money|\d+ ?% (daily|weekly|monthly) (returns?|profit)|(crypto|forex|stock|ipo)[^.\n]{0,25}(tips|vip|signals?) (group|channel)|risk[- ]free (profit|returns?)",
     "No legitimate investment guarantees high returns."),
    ("remote_app", "high", "Asks to install an app / screen sharing",
     r"\b(anydesk|teamviewer|quick ?support|rustdesk|airdroid|screen ?shar)|\.apk\b|install (this|the|our) app|download (this|the) app",
     "Remote-access apps and APK files let scammers control your phone and empty your bank account."),
    ("refund_mistake", "medium", "'Sent by mistake' refund request",
     r"(sent|transferred|credited)[^.\n]{0,25}by mistake|wrong(ly)? (transfer|credited)|please (return|refund|send back)",
     "Fake 'wrong transfer' messages trick you into sending your own money."),
    ("advance_fee", "high", "Pay a fee to receive money / prize / loan",
     r"(processing|registration|clearance|release|delivery|verification|tax|gst) (fee|charge|amount)[^.\n]{0,60}(claim|receive|release|prize|loan|parcel|job|refund)|(pay|deposit|transfer)[^.\n]{0,30}(fee|charges?)[^.\n]{0,30}(to|before) (claim|receive|release|get)|to claim[^.\n]{0,30}\bpay\b",
     "Paying money upfront to 'unlock' a prize, loan, job or parcel is the oldest scam there is."),
    ("gift_card", "high", "Payment by gift card / crypto",
     r"gift ?cards?|google play (card|code)|itunes card|pay (in|with|via) (bitcoin|usdt|crypto)",
     "Gift cards and crypto are untraceable, which is why scammers ask for them."),
    ("click_link", "low", "Pushes you to click a link",
     r"\b(click|tap|visit|open|follow)\b[^.\n]{0,25}\b(link|below|here|url)\b",
     "Links in unexpected messages often lead to fake login pages."),
]


def registered_domain(host: str) -> str:
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "gov", "net", "org", "ac", "nic", "bank", "res", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def extract_entities(text: str) -> dict:
    upis = sorted({m.group(0) for m in UPI_RE.finditer(text)})
    emails = sorted({m.group(0) for m in EMAIL_RE.finditer(text) if m.group(0) not in upis})
    scrubbed = EMAIL_RE.sub(" ", text)
    urls = []
    for m in URL_RE.finditer(scrubbed):
        u = m.group(0).rstrip(".,;:!?")
        if re.fullmatch(r"\d+(\.\d+)+", u):  # amounts like 1.5 or 2.000
            continue
        urls.append(u)
    urls = list(dict.fromkeys(urls))
    domains = []
    for u in urls:
        host = urlparse(u if "://" in u else "http://" + u).hostname or ""
        if host:
            domains.append(host.lower().removeprefix("www."))
    phones = list(dict.fromkeys(re.sub(r"[\s-]", "", m.group(0)) for m in PHONE_RE.finditer(text)))
    brands = list(dict.fromkeys(m.group(0).lower() for m in BRAND_WORDS.finditer(text)))
    return {
        "urls": urls,
        "domains": list(dict.fromkeys(domains)),
        "phone_numbers": phones,
        "upi_ids": upis,
        "emails": emails,
        "brands_mentioned": brands,
    }


def _matches_unnegated(pattern: str, text: str):
    for m in re.finditer(pattern, text, re.IGNORECASE):
        if not NEGATION.search(text[max(0, m.start() - 40) : m.start()]):
            return m
    return None


def analyze(text: str, entities: dict | None = None) -> dict:
    entities = entities or extract_entities(text)
    signals = []

    def add(sid, sev, title, detail, evidence=None):
        signals.append({"id": sid, "severity": sev, "title": title, "detail": detail, "match": evidence})

    for sid, sev, title, pattern, why in TEXT_RULES:
        m = _matches_unnegated(pattern, text)
        if m:
            add(sid, sev, title, why, m.group(0)[:80])

    for url in entities["urls"]:
        parsed = urlparse(url if "://" in url else "http://" + url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if not host:
            continue
        reg = registered_domain(host)
        tld = host.rsplit(".", 1)[-1]
        if reg in SHORTENERS:
            add("shortener", "medium", "Shortened link hides the real website",
                f"{host} is a URL shortener. You can't see where it really goes.", url)
        if re.fullmatch(r"[\d.]+", host):
            add("ip_link", "high", "Link points to a raw IP address", "Genuine companies use named websites.", url)
        if "xn--" in host:
            add("punycode", "high", "Look-alike characters in website name",
                "The domain uses special characters to imitate a real brand.", url)
        if tld in RISKY_TLDS:
            add("risky_tld", "medium", f"Unusual website ending (.{tld})",
                f".{tld} domains are cheap and heavily used for phishing.", url)
        if url.lower().startswith("http://"):
            add("no_https", "low", "Link is not secure (http)", "Official login pages always use https.", url)
        for brand, officials in OFFICIAL_DOMAINS.items():
            if brand in host.replace("-", "").replace(".", "") and not any(
                host == d or host.endswith("." + d) for d in officials
            ):
                add("lookalike", "high", f"Fake '{brand.upper()}' website",
                    f"{host} contains '{brand}' but is NOT an official domain ({', '.join(officials)}).", url)
                break
        if re.search(r"gov", host) and not re.search(r"\.gov(\.[a-z]{2})?$", host):
            add("fake_gov", "high", "Pretends to be a government site",
                f"{host} uses 'gov' but real government sites end in .gov.in / .gov.", url)

    mobile_claim = any(re.fullmatch(r"(\+91)?[6-9]\d{9}", p) for p in entities["phone_numbers"])
    if mobile_claim and entities["brands_mentioned"]:
        add("mobile_as_official", "medium", "Organisation using a personal mobile number",
            f"The message claims to be from {entities['brands_mentioned'][0].title()} but gives a personal 10-digit mobile number.")

    weights = {"high": 30, "medium": 15, "low": 5}
    score = min(100, sum(weights[s["severity"]] for s in signals))
    return {"signals": signals, "score": score, "entities": entities}
