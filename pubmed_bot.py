import os
import re
import html
import requests
from xml.etree import ElementTree as ET

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

QUERY = r'''
(
    ("sickle cell disease"[Title/Abstract] OR "sickle cell"[Title/Abstract])
    AND (pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract])
)
OR
(
    (pain[Title/Abstract] OR "chronic pain"[Title/Abstract] OR "neuropathic pain"[Title/Abstract])
    AND (mitochondria[Title/Abstract] OR mitochondrial[Title/Abstract] OR ROS[Title/Abstract] OR "oxidative stress"[Title/Abstract])
)
OR
(
    (pain[Title/Abstract] OR "chronic pain"[Title/Abstract])
    AND (opioid[Title/Abstract] OR addiction[Title/Abstract] OR tolerance[Title/Abstract])
)
OR
(
    (pain[Title/Abstract] OR nociception[Title/Abstract])
    AND ("dorsal root ganglion"[Title/Abstract] OR DRG[Title/Abstract] OR "spinal cord"[Title/Abstract])
)
'''.strip()

LOOKBACK_DAYS = 7
SEARCH_RETMAX = 50
FINAL_TOP_N = 5

TOP_JOURNALS_STRONG = {
    "Nature", "Science", "Cell", "Nature Medicine", "Nature Neuroscience",
    "Neuron", "Brain", "Blood", "Pain", "JCI"
}

TOP_JOURNALS_FIELD = {
    "Free radical biology & medicine", "Redox biology", "Molecular neurobiology",
    "Journal of Neuroscience", "Neurobiology of Disease", "Glia",
    "Journal of Neuroinflammation", "Pain Reports"
}

LOW_PRIORITY_JOURNALS = {
    "Scientific reports", "Journal of ethnopharmacology", "Phytomedicine"
}

HIGH_VALUE_KEYWORDS = {
    "sickle cell": 8, "chronic pain": 7, "neuropathic pain": 7,
    "mitochondria": 6, "mitochondrial dysfunction": 7, "ros": 4,
    "opioid": 5, "addiction": 5, "drg": 5, "dorsal horn": 6
}

NEGATIVE_KEYWORDS = {
    "osteoarthritis": -5, "plant extract": -6, "herbal": -5
}

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch_pubmed(query, days, retmax):
    params = {
        "db": "pubmed", "term": query, "retmax": retmax,
        "sort": "pub date", "retmode": "json",
        "datetype": "pdat", "reldate": days,
    }
    r = requests.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=30)
    return r.json()["esearchresult"]["idlist"]


def efetch_details(pmids):
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    r = requests.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=30)
    root = ET.fromstring(r.text)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        papers.append({
            "pmid": pmid,
            "title": article.findtext(".//ArticleTitle", default="No title"),
            "journal": article.findtext(".//Journal/Title", default="Unknown"),
            "abstract": "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return papers


def score_paper(paper):
    score = 0
    text = f"{paper['title']} {paper['abstract']}".lower()
    
    # 저널 점수
    if paper["journal"] in TOP_JOURNALS_STRONG:
        score += 20
    elif paper["journal"] in TOP_JOURNALS_FIELD:
        score += 10
    elif paper["journal"] in LOW_PRIORITY_JOURNALS:
        score -= 6
    
    # 키워드
    for kw, val in HIGH_VALUE_KEYWORDS.items():
        if kw in text:
            score += val
    
    # 네거티브
    for kw, val in NEGATIVE_KEYWORDS.items():
        if kw in text:
            score += val
    
    return score


def rank_papers(papers):
    for p in papers:
        p["score"] = score_paper(p)
    return sorted(papers, key=lambda x: x["score"], reverse=True)[:FINAL_TOP_N]


def build_message(papers):
    if not papers:
        return "🧪 Daily Paper Alert\n\n오늘은 논문이 없습니다."
    
    lines = ["🧪 <b>Daily Paper Alert v3</b>", ""]
    for i, p in enumerate(papers, 1):
        lines.append(f"<b>{i}. {html.escape(p['title'][:80])}...</b>")
        lines.append(f"📰 {html.escape(p['journal'])} | ⭐ {p['score']}pts")
        lines.append(f"🔗 <a href='{p['url']}'>PubMed</a>\n")
    
    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True
    })


def main():
    pmids = esearch_pubmed(QUERY, LOOKBACK_DAYS, SEARCH_RETMAX)
    papers = efetch_details(pmids)
    selected = rank_papers(papers)
    send_telegram(build_message(selected))


if __name__ == "__main__":
    main()
