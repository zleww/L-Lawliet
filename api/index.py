from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schema for new user comment
class CommentSubmission(BaseModel):
    user_name: str
    comment: str

# 20 Laws Initial Dataset
LAWS_DATABASE = [
    {
        "id": 1,
        "ra_number": "RA 10175",
        "official_title": "Cybercrime Prevention Act of 2012",
        "plain_title": "Online Safety & Anti-Cybercrime Law",
        "category": "Technology & Crime",
        "year": 2012,
        "tldr_summary": "Protects people from online hacking, identity theft, cyber-bullying, and online libel.",
        "full_breakdown": "Covers illegal access to computers, online fraud, cybersex operations, child abuse online, and online defamation.",
        "why_it_matters": "Keeps your digital accounts, personal information, and reputation safe online.",
        "example_scenario": "If someone hacks your Facebook account or posts false malicious rumors about you online, they can be prosecuted under this law.",
        "penalties": "Fines from ₱200,000 to millions and 6 to 12+ years imprisonment depending on severity.",
        "target_audience": "All internet and social media users, businesses, and website owners.",
        "source_url": "https://www.officialgazette.gov.ph/2012/09/12/republic-act-no-10175/",
        "user_notes": [
            {"user_name": "Juan D.", "comment": "Remember that online libel carries higher penalties than printed libel."}
        ]
    },
    {
        "id": 2,
        "ra_number": "RA 10963",
        "official_title": "Tax Reform for Acceleration and Inclusion (TRAIN) Act",
        "plain_title": "Lower Income Tax & Excise Tax Rules",
        "category": "Finance & Taxes",
        "year": 2017,
        "tldr_summary": "Lowers personal income tax for most workers, but adds tax to sugary drinks, fuel, and cars.",
        "full_breakdown": "Individuals earning ₱250,000 or below annually pay 0% income tax. It restructured excise taxes across consumer goods.",
        "why_it_matters": "More take-home pay for standard wage earners, but slight price increases on sweetened drinks and transport.",
        "example_scenario": "If your annual salary is ₱240,000, no income tax is deducted from your monthly paycheck.",
        "penalties": "Standard Bureau of Internal Revenue (BIR) penalties, surcharges, and tax evasion charges.",
        "target_audience": "All employed workers, business owners, and consumers in the PH.",
        "source_url": "https://www.officialgazette.gov.ph/2017/12/19/republic-act-no-10963/",
        "user_notes": []
    },
    {
        "id": 3,
        "ra_number": "RA 11032",
        "official_title": "Ease of Doing Business and Efficient Government Service Delivery Act of 2018",
        "plain_title": "Anti-Red Tape & Faster Government Service Law",
        "category": "Governance & Business",
        "year": 2018,
        "tldr_summary": "Government offices must process simple transactions in 3 days, complex in 7 days, and highly technical in 20 days.",
        "full_breakdown": "Eliminates excessive bureaucracy, simplifies business permits, and penalizes government employees who delay processing unreasonably.",
        "why_it_matters": "Saves you time and cuts corruption when applying for government permits, clearances, and documents.",
        "example_scenario": "Applying for a simple barangay or city clearance shouldn't take weeks; agencies must release it within 3 working days.",
        "penalties": "6 months suspension for 1st offense; dismissal, fine up to ₱2,000,000, and jail time (1-6 years) for 2nd offense.",
        "target_audience": "Citizens dealing with government offices, business applicants.",
        "source_url": "https://www.officialgazette.gov.ph/2018/05/28/republic-act-no-11032/",
        "user_notes": []
    },
    {
        "id": 4,
        "ra_number": "RA 11313",
        "official_title": "Safe Spaces Act (Bawal Bastos Law)",
        "plain_title": "Anti-Catcalling & Gender-Based Harassment Law",
        "category": "Social & Welfare",
        "year": 2019,
        "tldr_summary": "Penalizes gender-based sexual harassment in streets, public spaces, online, workplaces, and educational institutions.",
        "full_breakdown": "Covers wolf-whistling, catcalling, unwanted physical touching, persistent uninvited remarks, and cyber-flashing online.",
        "why_it_matters": "Ensures public and digital spaces are safe, respectful, and free from verbal or physical harassment for everyone.",
        "example_scenario": "If someone makes unwanted lewd comments or unwelcome gestures toward you in public or online, it is punishable by law.",
        "penalties": "Community service, fines ranging from ₱10,000 to ₱500,000, and imprisonment depending on the gravity of the offense.",
        "target_audience": "All citizens, students, employees, public transport operators, and online users.",
        "source_url": "https://www.officialgazette.gov.ph/2019/04/17/republic-act-no-11313/",
        "user_notes": []
    },
    {
        "id": 5,
        "ra_number": "RA 9994",
        "official_title": "Expanded Senior Citizens Act of 2010",
        "plain_title": "Senior Citizens Benefits & 20% Discount Law",
        "category": "Social & Welfare",
        "year": 2010,
        "tldr_summary": "Grants senior citizens a 20% discount and VAT exemption on medicines, medical services, transport, and public utilities.",
        "full_breakdown": "Provides senior citizens privileges including monthly stipends for indigents, free medical/dental services, and prioritization in establishments.",
        "why_it_matters": "Provides financial relief and social protection for elderly Filipinos who have contributed to society.",
        "example_scenario": "When a senior citizen buys prescribed medicines or eats at a restaurant, they are entitled to a 20% discount plus VAT exemption upon presenting their Senior Citizen ID.",
        "penalties": "Fines from ₱50,000 to ₱200,000 and imprisonment for business owners who refuse to grant senior discounts.",
        "target_audience": "Senior citizens (aged 60 and above), families, and all commercial establishments.",
        "source_url": "https://www.officialgazette.gov.ph/2010/02/15/republic-act-no-9994/",
        "user_notes": []
    }
    # (Add the remaining 17 laws following this identical 14-field structure)
]

@app.get("/api/laws")
def get_laws(search: Optional[str] = None):
    """Fetch laws with optional keyword filtering"""
    if not search:
        return LAWS_DATABASE
    
    query = search.lower()
    filtered = [
        law for law in LAWS_DATABASE
        if query in law["ra_number"].lower()
        or query in law["plain_title"].lower()
        or query in law["category"].lower()
        or query in law["tldr_summary"].lower()
    ]
    return filtered

@app.get("/api/laws/{law_id}")
def get_law_detail(law_id: int):
    """Fetch single law with full 14 fields"""
    law = next((l for l in LAWS_DATABASE if l["id"] == law_id), None)
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")
    return law

@app.post("/api/laws/{law_id}/comments")
def add_user_comment(law_id: int, payload: CommentSubmission):
    """Add a user tip or comment to a specific law"""
    law = next((l for l in LAWS_DATABASE if l["id"] == law_id), None)
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")
    
    new_comment = {"user_name": payload.user_name, "comment": payload.comment}
    law["user_notes"].append(new_comment)
    return {"message": "Knowledge added successfully!", "comments": law["user_notes"]}