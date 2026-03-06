import os
import re
import html
import requests
from xml.etree import ElementTree as ET

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# =========================
# 1) PubMed 검색식
# =========================
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

LOOKBACK_DAYS = 7
SEARCH_RETMAX = 50
FINAL_TOP_N = 5

# =========================
# 2) 저널 우선순위
# =========================
TOP_JOURNALS_STRONG = {
    "Nature", "Science", "Cell", "Nature Medicine", "Nature Neuroscience",
    "Nature Communications", "Science Advances", "Science Translational Medicine",
    "Neuron", "Brain", "Blood", "The Journal of Clinical Investigation",
    "JCI Insight", "Pain", "Cell Reports Medicine", "Cell Reports",
    "PNAS",
}

# =========================
# 3) 카테고리 분류 규칙
# =========================
CATEGORIES = {
    "sickle_cell_pain": {
        "keywords": ["sickle cell", "sickle-cell", "scd", "hbss"],
        "required": ["pain", "chronic pain", "neuropathic pain", "nociception", "hyperalgesia", "allodynia"]
    },
    "chronic_pain_mechanism": {
        "keywords": ["chronic pain", "persistent pain", "pain mechanism", "pain signaling", "sensitization"],
        "exclude": ["sickle cell"]
    },
    "mitochondria_ros": {
        "keywords": ["mitochondria", "mitochondrial", "ros", "oxidative stress", "bioenergetics", "oxphos"],
        "required": ["pain", "chronic pain", "neuropathic pain"]
    },
    "opioid_addiction": {
        "keywords": ["opioid", "addiction", "dependence", "oud", "tolerance", "analgesia"],
        "required": ["pain"]
    },
    "pain_circuit_region": {
        "keywords": ["drg", "dorsal root ganglion", "dorsal horn", "spinal cord", "thalamus", 
                     "amygdala", "insula", "acc", "pag", "periaqueductal", "nucleus accumbens",
                     "hippocampus", "prefrontal cortex"],
        "required": ["pain", "nociception"]
    }
}

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch_pubmed(query, days, retmax):
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "sort": "pub date",
        "retmode": "json",
        "datetype": "pdat",
        "reldate": days,
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
        title = article.findtext(".//ArticleTitle", default="No title")
        journal = article.findtext(".//Journal/Title", default="Unknown")
        abstract_parts = article.findall(".//Abstract/AbstractText")
        abstract = " ".join("".join(x.itertext()) for x in abstract_parts) if abstract_parts else ""
        
        papers.append({
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "abstract": abstract,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return papers


def classify_paper(paper):
    """논문을 카테고리별로 분류"""
    text = f"{paper['title']} {paper['abstract']}".lower()
    categories = []
    
    for cat_name, rules in CATEGORIES.items():
        keywords = rules.get("keywords", [])
        required = rules.get("required", [])
        exclude = rules.get("exclude", [])
        
        # 키워드 매칭
        keyword_match = any(kw.lower() in text for kw in keywords)
        
        # required 조건 확인
        required_match = all(req.lower() in text for req in required) if required else True
        
        # exclude 조건 확인
        exclude_match = not any(ex.lower() in text for ex in exclude) if exclude else True
        
        if keyword_match and required_match and exclude_match:
            categories.append(cat_name)
    
    return categories if categories else ["other"]


def score_paper(paper):
    """논문 점수 계산"""
    score = 0
    text = f"{paper['title']} {paper['abstract']}".lower()
    
    # 저널 점수
    if paper["journal"] in TOP_JOURNALS_STRONG:
        score += 15
    
    # 키워드 점수
    keyword_scores = {
        "sickle cell": 5, "mitochondria": 4, "mitochondrial": 4,
        "ros": 3, "oxidative stress": 3, "opioid": 3,
        "addiction": 3, "drg": 3, "neuropathic pain": 3,
        "chronic pain": 2, "pain": 1
    }
    
    for kw, val in keyword_scores.items():
        if kw in text:
            score += val
    
    return score


def select_portfolio(papers):
    """카테고리별 1개씩 + 나머지는 점수순"""
    # 카테고리 분류
    categorized = {cat: [] for cat in CATEGORIES.keys()}
    categorized["other"] = []
    
    for paper in papers:
        cats = classify_paper(paper)
        paper["categories"] = cats
        paper["score"] = score_paper(paper)
        
        # 첫 번째 카테고리에 배치
        primary_cat = cats[0]
        if primary_cat in categorized:
            categorized[primary_cat].append(paper)
        else:
            categorized["other"].append(paper)
    
    # 각 카테고리에서 최고 점수 1개씩 선택
    selected = []
    for cat_name in CATEGORIES.keys():
        if categorized[cat_name]:
            best = max(categorized[cat_name], key=lambda x: x["score"])
            best["primary_category"] = cat_name
            selected.append(best)
    
    # 남은 자리는 전체 점수순으로 채움
    remaining = [p for p in papers if p not in selected]
    remaining.sort(key=lambda x: x["score"], reverse=True)
    
    for p in remaining:
        if len(selected) >= FINAL_TOP_N:
            break
        p["primary_category"] = p["categories"][0] if p["categories"] else "other"
        selected.append(p)
    
    return selected[:FINAL_TOP_N]


def build_message(papers):
    if not papers:
        return "🧪 Daily Paper Alert\n\n오늘은 조건에 맞는 논문이 없습니다."
    
    lines = ["🧪 <b>Daily Paper Alert (v3)</b>", ""]
    lines.append("카테고리별 대표 논문 + 전체 점수순")
    lines.append("")
    
    cat_names = {
        "sickle_cell_pain": "🩸 Sickle Cell Pain",
        "chronic_pain_mechanism": "🔬 Chronic Pain Mechanism",
        "mitochondria_ros": "⚡ Mitochondria/ROS",
        "opioid_addiction": "💊 Opioid/Addiction",
        "pain_circuit_region": "🧠 Pain Circuit/Region",
        "other": "📄 Other"
    }
    
    for i, p in enumerate(papers, 1):
        cat = cat_names.get(p.get("primary_category", "other"), "📄 Other")
        title = html.escape(p['title'][:100] + "..." if len(p['title']) > 100 else p['title'])
        journal = html.escape(p['journal'])
        
        lines.append(f"<b>{i}. [{cat}]</b>")
        lines.append(f"   {title}")
        lines.append(f"   📰 {journal} | ⭐ {p['score']}pts")
        lines.append(f"   🔗 <a href=\"{p['url']}\">PubMed</a>")
        lines.append("")
    
    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=30)
    return r.json()


def main():
    pmids = esearch_pubmed(QUERY, LOOKBACK_DAYS, SEARCH_RETMAX)
    papers = efetch_details(pmids)
    selected = select_portfolio(papers)
    message = build_message(selected)
    send_telegram(message)


if __name__ == "__main__":
    main()
