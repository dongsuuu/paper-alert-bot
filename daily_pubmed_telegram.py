import os
import re
import html
import requests
from datetime import datetime
from xml.etree import ElementTree as ET

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

QUERY = r'''
(
    (
        "sickle cell disease"[Title/Abstract] OR "sickle cell"[Title/Abstract]
    )
    AND (
        pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract]
        OR nociception[Title/Abstract] OR hyperalgesia[Title/Abstract] OR allodynia[Title/Abstract]
        OR sensitization[Title/Abstract]
    )
)
OR
(
    (
        pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract]
        OR nociception[Title/Abstract] OR hyperalgesia[Title/Abstract] OR allodynia[Title/Abstract]
        OR sensitization[Title/Abstract]
    )
    AND (
        mitochondria[Title/Abstract] OR mitochondrial[Title/Abstract]
        OR "mitochondrial dysfunction"[Title/Abstract] OR "mitochondrial function"[Title/Abstract]
        OR ROS[Title/Abstract] OR "oxidative stress"[Title/Abstract] OR metabolism[Title/Abstract]
        OR bioenergetics[Title/Abstract] OR OXPHOS[Title/Abstract]
    )
)
OR
(
    (
        pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract]
    )
    AND (
        opioid[Title/Abstract] OR addiction[Title/Abstract] OR dependence[Title/Abstract]
        OR "opioid use disorder"[Title/Abstract] OR analgesia[Title/Abstract] OR tolerance[Title/Abstract]
    )
)
OR
(
    (
        pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract]
        OR nociception[Title/Abstract]
    )
    AND (
        "dorsal root ganglion"[Title/Abstract] OR DRG[Title/Abstract] OR "dorsal horn"[Title/Abstract]
        OR "spinal cord"[Title/Abstract] OR thalamus[Title/Abstract] OR amygdala[Title/Abstract]
        OR insula[Title/Abstract] OR "anterior cingulate cortex"[Title/Abstract]
        OR PAG[Title/Abstract] OR "periaqueductal gray"[Title/Abstract]
        OR "nucleus accumbens"[Title/Abstract] OR hippocampus[Title/Abstract]
        OR "prefrontal cortex"[Title/Abstract]
    )
)
'''.strip()

SEARCH_RETMAX = 120
FINAL_TOP_N = 5

TOP_JOURNALS_STRONG = {
    "Nature", "Science", "Cell", "Nature Medicine", "Nature Neuroscience",
    "Nature Communications", "Science Advances", "Science Translational Medicine",
    "Neuron", "Brain", "Blood", "The Journal of Clinical Investigation",
    "JCI Insight", "Pain", "Cell Reports Medicine", "Cell Reports",
    "Proceedings of the National Academy of Sciences of the United States of America",
    "PNAS",
}

TOP_JOURNALS_FIELD = {
    "Free radical biology & medicine", "Redox biology", "Molecular neurobiology",
    "Journal of Neuroscience", "Neurobiology of Disease", "Glia",
    "Brain, behavior, and immunity", "Journal of Neuroinflammation",
    "Neuroscience", "Pain Reports", "Frontiers in Pain Research",
    "Acta Neuropathologica", "Acta Neuropathologica Communications",
    "Journal of Pain Research", "Journal of Headache and Pain",
    "Brain research", "Experimental neurology", "Addiction Biology",
    "Biological Psychiatry", "Neuropsychopharmacology",
}

LOW_PRIORITY_JOURNALS = {
    "Scientific reports", "Chinese journal of natural medicines",
    "Journal of ethnopharmacology", "Phytomedicine",
    "Evidence-based complementary and alternative medicine",
}

HIGH_VALUE_KEYWORDS = {
    "sickle cell": 8, "sickle cell disease": 8, "chronic pain": 7,
    "neuropathic pain": 7, "central sensitization": 7, "pain sensitization": 6,
    "nociception": 5, "hyperalgesia": 5, "allodynia": 5,
    "mitochondria": 6, "mitochondrial": 6, "mitochondrial dysfunction": 7,
    "oxidative stress": 5, "ros": 4, "bioenergetics": 4, "oxphos": 4,
    "opioid": 5, "opioid use disorder": 7, "addiction": 5,
    "dependence": 4, "tolerance": 4, "microglia": 4, "astrocyte": 3,
    "macrophage": 3, "sensory neuron": 5, "nociceptor": 5,
}

ANATOMY_KEYWORDS = {
    "drg": 5, "dorsal root ganglion": 6, "spinal cord": 5,
    "dorsal horn": 6, "thalamus": 4, "amygdala": 4,
    "anterior cingulate cortex": 5, "insula": 4,
    "periaqueductal gray": 5, "pag": 3, "nucleus accumbens": 4,
    "vta": 4, "hippocampus": 3, "prefrontal cortex": 4,
}

STRONG_NEGATIVE_KEYWORDS = {
    "quality of life": -12, "healthcare utilization": -15,
    "health care utilization": -15, "social determinants": -15,
    "disparities": -15, "survey": -12, "prevalence": -10,
    "incidence": -10, "epidemiology": -12, "policy": -15,
    "guideline": -12, "education": -10, "commentary": -12,
    "perspective": -10, "case report": -15, "retrospective cohort": -8,
    "database study": -10, "claims data": -12, "questionnaire": -12,
    "stigma": -12, "insurance": -12, "adherence": -10, "qualitative": -15,
}

CATEGORY_NAMES = [
    "sickle_cell_pain", "chronic_pain_mechanism", "mitochondria_ros",
    "opioid_addiction", "pain_circuit_region",
]

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch_pubmed(query: str, retmax: int):
    current_year = datetime.now().year
    start_year = current_year - 5
    params = {
        "db": "pubmed",
        "term": f"({query}) AND (\"{start_year}/01/01\"[Date - Publication] : \"3000\"[Date - Publication])",
        "retmax": retmax,
        "sort": "relevance",
        "retmode": "json",
        "tool": "paper_alert_bot",
        "email": "your_email@example.com",
    }
    r = requests.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["esearchresult"]["idlist"]


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def efetch_details(pmids):
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": "paper_alert_bot",
        "email": "your_email@example.com",
    }
    r = requests.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        title = article.findtext(".//ArticleTitle", default="No title")
        journal = article.findtext(".//Journal/Title", default="Unknown journal")
        pmid = article.findtext(".//PMID", default="")
        year = article.findtext(".//PubDate/Year")
        medline_date = article.findtext(".//PubDate/MedlineDate")
        pub_date = clean_text(year or medline_date or "Unknown date")
        abstract_parts = article.findall(".//Abstract/AbstractText")
        abstract = " ".join(clean_text("".join(x.itertext())) for x in abstract_parts) if abstract_parts else ""
        publication_types = [
            clean_text(pt.text or "")
            for pt in article.findall(".//PublicationType")
            if clean_text(pt.text or "")
        ]
        papers.append({
            "title": clean_text(title),
            "journal": clean_text(journal),
            "pmid": clean_text(pmid),
            "pub_date": pub_date,
            "abstract": abstract,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "publication_types": publication_types,
        })
    return papers


def get_text_blob(paper):
    return f"{paper['title']} {paper['abstract']}".lower()


def category_scores(text: str):
    scores = {
        "sickle_cell_pain": 0,
        "chronic_pain_mechanism": 0,
        "mitochondria_ros": 0,
        "opioid_addiction": 0,
        "pain_circuit_region": 0,
    }
    if "sickle cell" in text:
        scores["sickle_cell_pain"] += 10
    if "pain" in text or "chronic pain" in text or "neuropathic pain" in text:
        scores["sickle_cell_pain"] += 4
    for kw in ["chronic pain", "neuropathic pain", "central sensitization", "sensitization", "nociception", "hyperalgesia", "allodynia"]:
        if kw in text:
            scores["chronic_pain_mechanism"] += 4
    for kw in ["mitochondria", "mitochondrial", "mitochondrial dysfunction", "ros", "oxidative stress", "bioenergetics", "oxphos", "metabolism"]:
        if kw in text:
            scores["mitochondria_ros"] += 4
    for kw in ["opioid", "addiction", "opioid use disorder", "dependence", "tolerance", "analgesia"]:
        if kw in text:
            scores["opioid_addiction"] += 4
    for kw in [
        "drg", "dorsal root ganglion", "spinal cord", "dorsal horn",
        "thalamus", "amygdala", "insula", "anterior cingulate cortex",
        "periaqueductal gray", "pag", "nucleus accumbens", "vta",
        "hippocampus", "prefrontal cortex", "sensory neuron", "nociceptor",
        "microglia", "astrocyte"
    ]:
        if kw in text:
            scores["pain_circuit_region"] += 4
    return scores


def assign_primary_category(paper):
    text = get_text_blob(paper)
    scores = category_scores(text)
    primary = max(scores, key=scores.get)
    if scores[primary] == 0:
        return "chronic_pain_mechanism"
    return primary


def is_mechanistic_bonus(text: str):
    mech_terms = [
        "mechanism", "pathway", "signaling", "neuron", "microglia",
        "astrocyte", "macrophage", "mitochondria", "oxidative stress",
        "ros", "sensitization", "dorsal horn", "drg", "spinal cord", "thalamus", "amygdala"
    ]
    return sum(1 for t in mech_terms if t in text)


def score_paper(paper):
    score = 0
    text = get_text_blob(paper)
    if paper["journal"] in TOP_JOURNALS_STRONG:
        score += 20
    elif paper["journal"] in TOP_JOURNALS_FIELD:
        score += 10
    elif paper["journal"] in LOW_PRIORITY_JOURNALS:
        score -= 6
    for kw, val in HIGH_VALUE_KEYWORDS.items():
        if kw in text:
            score += val
    for kw, val in ANATOMY_KEYWORDS.items():
        if kw in text:
            score += val
    for kw, val in STRONG_NEGATIVE_KEYWORDS.items():
        if kw in text:
            score += val
    if ("sickle cell" in text) and ("pain" in text or "chronic pain" in text or "neuropathic pain" in text):
        score += 12
    if ("pain" in text or "chronic pain" in text or "neuropathic pain" in text) and (
        "mitochondria" in text or "mitochondrial" in text or "ros" in text or "oxidative stress" in text
    ):
        score += 8
    if ("pain" in text or "chronic pain" in text) and (
        "opioid" in text or "addiction" in text or "opioid use disorder" in text or "tolerance" in text
    ):
        score += 7
    score += is_mechanistic_bonus(text)
    title_lower = paper["title"].lower()
    for term in ["sickle", "pain", "chronic pain", "neuropathic pain", "mitochond", "ros", "opioid", "addiction", "dorsal horn", "drg"]:
        if term in title_lower:
            score += 2
    pub_types_lower = " ".join(paper.get("publication_types", [])).lower()
    if "review" in pub_types_lower:
        score -= 1
    if "systematic review" in pub_types_lower:
        score -= 3
    if "meta-analysis" in pub_types_lower:
        score -= 4
    if "case reports" in pub_types_lower:
        score -= 8
    return score


def rank_papers_balanced(papers):
    for p in papers:
        p["score"] = score_paper(p)
        p["category"] = assign_primary_category(p)
    filtered = [p for p in papers if p["score"] >= 8]
    cat_buckets = {cat: [] for cat in CATEGORY_NAMES}
    for p in filtered:
        cat_buckets[p["category"]].append(p)
    for cat in CATEGORY_NAMES:
        cat_buckets[cat] = sorted(cat_buckets[cat], key=lambda x: x["score"], reverse=True)
    selected = []
    selected_pmids = set()
    for cat in CATEGORY_NAMES:
        for p in cat_buckets[cat]:
            if p["pmid"] not in selected_pmids:
                selected.append(p)
                selected_pmids.add(p["pmid"])
                break
        if len(selected) >= FINAL_TOP_N:
            return selected[:FINAL_TOP_N]
    all_ranked = sorted(filtered, key=lambda x: x["score"], reverse=True)
    for p in all_ranked:
        if p["pmid"] not in selected_pmids:
            selected.append(p)
            selected_pmids.add(p["pmid"])
            if len(selected) >= FINAL_TOP_N:
                break
    return selected[:FINAL_TOP_N]


def shorten(text, max_len=220):
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def pretty_category(cat):
    mapping = {
        "sickle_cell_pain": "Sickle cell pain",
        "chronic_pain_mechanism": "Chronic pain mechanism",
        "mitochondria_ros": "Mitochondria / ROS",
        "opioid_addiction": "Opioid / addiction",
        "pain_circuit_region": "Pain circuit / region",
    }
    return mapping.get(cat, cat)


def build_message(papers):
    if not papers:
        return (
            "🧪 <b>Daily Paper Alert v4</b>\n\n"
            "오늘은 최근 5년 안에서 조건에 맞는 relevant paper를 찾지 못했어."
        )
    lines = []
    lines.append("🧪 <b>Daily Paper Alert v4</b>")
    lines.append("Focus: relevant papers from the last 5 years")
    lines.append("")
    for i, p in enumerate(papers, 1):
        summary = shorten(p["abstract"], 220) if p["abstract"] else "Abstract not available."
        pub_type = ", ".join(p["publication_types"][:3]) if p["publication_types"] else "N/A"
        lines.append(f"<b>{i}. {html.escape(p['title'])}</b>")
        lines.append(f"• Category: {html.escape(pretty_category(p['category']))}")
        lines.append(f"• Journal: {html.escape(p['journal'])}")
        lines.append(f"• Date: {html.escape(p['pub_date'])}")
        lines.append(f"• PMID: {html.escape(p['pmid'])}")
        lines.append(f"• Type: {html.escape(pub_type)}")
        lines.append(f"• Score: {p['score']}")
        lines.append(f"• Summary: {html.escape(summary)}")
        lines.append(f"• <a href=\"{html.escape(p['url'])}\">PubMed link</a>")
        lines.append("")
    return "\n".join(lines)


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    pmids = esearch_pubmed(QUERY, SEARCH_RETMAX)
    papers = efetch_details(pmids)
    selected = rank_papers_balanced(papers)
    message = build_message(selected)
    send_telegram_message(message)


if __name__ == "__main__":
    main()
