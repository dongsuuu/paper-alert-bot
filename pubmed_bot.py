import os
import re
import html
import requests
from xml.etree import ElementTree as ET

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# 원하는 키워드
QUERY = r'''
(
    ("pain"[Title/Abstract] OR "chronic pain"[Title/Abstract] OR nociception[Title/Abstract] 
     OR "neuropathic pain"[Title/Abstract] OR DRG[Title/Abstract] 
     OR "dorsal root ganglion"[Title/Abstract])
    OR ("addiction"[Title/Abstract] OR "opioid use disorder"[Title/Abstract] 
        OR opioid[Title/Abstract])
)
AND (
    mitochondria[Title/Abstract] OR "mitochondrial function"[Title/Abstract] 
    OR "mitochondrial dysfunction"[Title/Abstract] OR ROS[Title/Abstract] 
    OR "oxidative stress"[Title/Abstract] OR "sickle cell disease"[Title/Abstract] 
    OR "sickle cell"[Title/Abstract]
)
'''.strip()

# 최근 며칠 안의 논문을 볼지
LOOKBACK_DAYS = 7

# PubMed에서 처음 가져올 최대 개수
SEARCH_RETMAX = 25

# 최종 텔레그램으로 별할 개수
FINAL_TOP_N = 5

# 저널 우선순위
TOP_JOURNALS = {
    "Nature", "Science", "Cell", "Nature Medicine", "Nature Neuroscience",
    "Nature Communications", "Science Advances", "Science Translational Medicine",
    "Neuron", "Brain", "Blood", "The Journal of Clinical Investigation",
    "JCI Insight", "Pain", "Cell Reports Medicine", "Cell Reports",
    "Proceedings of the National Academy of Sciences of the United States of America",
    "PNAS",
}

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch_pubmed(query: str, days: int, retmax: int):
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "sort": "pub date",
        "retmode": "json",
        "datetype": "pdat",
        "reldate": days,
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
        doi = ""
        for aid in article.findall(".//ArticleId"):
            if aid.attrib.get("IdType") == "doi":
                doi = clean_text(aid.text or "")
                break
        papers.append({
            "title": clean_text(title),
            "journal": clean_text(journal),
            "pmid": clean_text(pmid),
            "pub_date": pub_date,
            "abstract": abstract,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return papers


def score_paper(paper):
    score = 0
    text = f"{paper['title']} {paper['abstract']}".lower()
    
    # 키워드 점수
    keywords = {
        "pain": 2, "chronic pain": 2, "neuropathic pain": 3,
        "dorsal root ganglion": 3, "drg": 2,
        "addiction": 2, "opioid": 2,
        "mitochondria": 3, "mitochondrial": 3,
        "ros": 2, "oxidative stress": 2, "sickle cell": 3,
    }
    for kw, val in keywords.items():
        if kw in text:
            score += val
    
    # 저널 우선순위 점수
    if paper["journal"] in TOP_JOURNALS:
        score += 10
    
    # 제목에 직접적으로 들어가면 가산
    title_lower = paper["title"].lower()
    for boost_kw in ["mitochond", "pain", "sickle", "opioid", "addiction", "drg"]:
        if boost_kw in title_lower:
            score += 1
    
    return score


def rank_papers(papers):
    ranked = sorted(papers, key=lambda p: score_paper(p), reverse=True)
    return ranked[:FINAL_TOP_N]


def shorten(text, max_len=260):
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_message(papers):
    if not papers:
        return (
            "🧪 Daily Paper Alert\n\n"
            "오늘은 조건에 맞는 최근 PubMed 논문을 찾지 못했어."
        )
    lines = []
    lines.append("🧪 <b>Daily Paper Alert</b>")
    lines.append("Topics: pain / addiction / mitochondrial function / sickle cell disease")
    lines.append("")
    for i, p in enumerate(papers, 1):
        summary = shorten(p["abstract"], 240) if p["abstract"] else "Abstract not available."
        lines.append(f"<b>{i}. {html.escape(p['title'])}</b>")
        lines.append(f"• Journal: {html.escape(p['journal'])}")
        lines.append(f"• Date: {html.escape(p['pub_date'])}")
        lines.append(f"• PMID: {html.escape(p['pmid'])}")
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
    pmids = esearch_pubmed(QUERY, LOOKBACK_DAYS, SEARCH_RETMAX)
    papers = efetch_details(pmids)
    selected = rank_papers(papers)
    message = build_message(selected)
    send_telegram_message(message)


if __name__ == "__main__":
    main()
