"""Prompt builder for the autonomous job application agent.

Constructs the full instruction prompt that tells Claude Code / the AI agent
how to fill out a job application form using Playwright MCP tools. All
personal data is loaded from the user's profile -- nothing is hardcoded.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from applypilot import config
from applypilot.database import get_all_qa

logger = logging.getLogger(__name__)


def _build_profile_summary(profile: dict) -> str:
    """Format the applicant profile section of the prompt.

    Reads all relevant fields from the profile dict and returns a
    human-readable multi-line summary for the agent.
    """
    p = profile
    personal = p["personal"]
    work_auth = p["work_authorization"]
    comp = p["compensation"]
    exp = p.get("experience", {})
    avail = p.get("availability", {})
    eeo = p.get("eeo_voluntary", {})

    lines = [
        f"Name: {personal['full_name']}",
    ]
    if personal.get("title"):
        lines.append(f"Title/Prefix: {personal['title']}")
    lines.extend([
        f"Email: {personal['email']}",
        f"Phone: {personal['phone']}",
    ])

    # Address -- structured for form fields
    lines.append(f"Street Address: {personal.get('address', '')}")
    lines.append(f"City: {personal.get('city', '')}")
    lines.append(f"State/Province: {personal.get('province_state', '')}")
    lines.append(f"Postal Code: {personal.get('postal_code', '')}")
    lines.append(f"Country: {personal.get('country', '')}")
    # Full address (for single-line fields)
    addr_parts = [
        personal.get("address", ""),
        personal.get("city", ""),
        personal.get("province_state", ""),
        personal.get("postal_code", ""),
        personal.get("country", ""),
    ]
    lines.append(f"Full Address: {', '.join(p for p in addr_parts if p)}")

    if personal.get("linkedin_url"):
        lines.append(f"LinkedIn: {personal['linkedin_url']}")
    if personal.get("github_url"):
        lines.append(f"GitHub: {personal['github_url']}")
    if personal.get("portfolio_url"):
        lines.append(f"Portfolio: {personal['portfolio_url']}")
    if personal.get("website_url"):
        lines.append(f"Website: {personal['website_url']}")

    # Work authorization
    lines.append(f"Work Auth: {work_auth.get('legally_authorized_to_work', 'See profile')}")
    lines.append(f"Sponsorship Needed: {work_auth.get('require_sponsorship', 'See profile')}")
    if work_auth.get("work_permit_type"):
        lines.append(f"Work Permit: {work_auth['work_permit_type']}")

    # Compensation
    currency = comp.get("salary_currency", "USD")
    lines.append(f"Salary Expectation: ${comp['salary_expectation']} {currency}")

    # Experience
    if exp.get("years_of_experience_total"):
        lines.append(f"Years Experience: {exp['years_of_experience_total']}")
    if exp.get("current_job_title"):
        lines.append(f"Most Recent Title: {exp['current_job_title']}")
    if exp.get("target_role"):
        lines.append(f"Target Role: {exp['target_role']}")
    if exp.get("education_level"):
        lines.append(f"Education: {exp['education_level']}")

    # Certifications (from resume_facts)
    resume_facts = p.get("resume_facts", {})
    certs = resume_facts.get("certifications", [])
    if certs:
        lines.append(f"Certifications: {', '.join(certs)}")

    # Skills summary (from skills_boundary — helps agent answer "Do you have experience with X?")
    boundary = p.get("skills_boundary", {})
    if boundary:
        for category, skills in boundary.items():
            if isinstance(skills, list) and skills:
                lines.append(f"Skills ({category}): {', '.join(skills)}")

    # Title variants by company (for "most recent title" / "previous titles" questions)
    title_variants = resume_facts.get("title_variants", {})
    if title_variants:
        titles = [f"{company}: {title}" for company, title in title_variants.items()]
        lines.append(f"Previous Titles: {'; '.join(titles)}")

    # Languages (with proficiency levels)
    languages = personal.get("languages", [])
    if languages:
        if isinstance(languages[0], dict):
            lang_parts = [f"{l['language']} ({l['proficiency']})" for l in languages]
            lines.append(f"Languages: {', '.join(lang_parts)}")
            # Also list just the language names for simple yes/no questions
            lines.append(f"Languages spoken: {', '.join(l['language'] for l in languages)}")
            lines.append("IMPORTANT: Do NOT claim proficiency in any language not listed above. If asked about a language not listed, answer NO / Not proficient.")
        else:
            lines.append(f"Languages: {', '.join(languages)}")

    # Availability
    lines.append(f"Available: {avail.get('earliest_start_date', 'Immediately')}")

    # Standard responses
    lines.extend([
        "Age 18+: Yes",
        "Background Check: Yes",
        "Felony: No",
        "Previously Worked Here: No",
        "How Heard: Online Job Board",
    ])

    # EEO
    lines.append(f"Gender: {eeo.get('gender', 'Decline to self-identify')}")
    lines.append(f"Sexual Orientation: {eeo.get('sexual_orientation', 'I do not wish to answer')}")
    lines.append(f"Transgender: {eeo.get('transgender', 'I do not wish to answer')}")
    dob = eeo.get('date_of_birth', '')
    if dob:
        lines.append(f"Date of Birth: {dob}")
    lines.append(f"Race/Ethnicity: {eeo.get('race_ethnicity', 'Decline to self-identify')}")
    hispanic = eeo.get('hispanic_latino', '')
    if hispanic:
        lines.append(f"Hispanic or Latino: {hispanic}")
    lines.append(f"Veteran: {eeo.get('veteran_status', 'I am not a protected veteran')}")
    disability = eeo.get('disability_status', 'No, I do not have a disability')
    disability_pressed = eeo.get('disability_if_pressed', '')
    if disability_pressed:
        lines.append(f"Disability: {disability} (if required to answer: {disability_pressed})")
    else:
        lines.append(f"Disability: {disability}")

    return "\n".join(lines)


def _build_location_check(profile: dict, search_config: dict) -> str:
    """Build the location eligibility check section of the prompt.

    Uses the accept_patterns from search config to determine which cities
    are acceptable for hybrid/onsite roles.
    """
    personal = profile["personal"]
    location_cfg = search_config.get("location", {})
    accept_patterns = location_cfg.get("accept_patterns", [])
    primary_city = personal.get("city", location_cfg.get("primary", "your city"))

    # Build the list of acceptable cities for hybrid/onsite
    if accept_patterns:
        city_list = ", ".join(accept_patterns)
    else:
        city_list = primary_city

    return f"""== LOCATION CHECK (do this FIRST before any form) ==
Read the job page. Determine the work arrangement. Then decide:
- "Remote" in the US or "work from anywhere" -> ELIGIBLE. Apply.
- "Remote" but restricted to a non-US country (e.g. "remote - Germany", "remote - EU only") -> NOT ELIGIBLE. Output RESULT:FAILED:not_eligible_location
- "Hybrid" or "onsite" in {city_list} -> ELIGIBLE. Apply.
- "Hybrid" or "onsite" in another US city BUT the posting also says "remote OK" or "remote option available" -> ELIGIBLE. Apply.
- "Onsite only" or "hybrid only" in any city outside the list above with NO remote option -> NOT ELIGIBLE. Stop immediately. Output RESULT:FAILED:not_eligible_location
- Job is in a non-US country (Germany, India, UK, Philippines, anywhere in Europe/Asia/etc.) -> NOT ELIGIBLE unless it explicitly says "US remote OK". Output RESULT:FAILED:not_eligible_location
- Job requires fluency in a language the candidate doesn't speak (see Languages in profile) -> NOT ELIGIBLE. Output RESULT:FAILED:not_eligible_location
- Cannot determine location -> Continue applying. If a screening question reveals it's non-local onsite, answer honestly and let the system reject if needed.
Do NOT fill out forms for jobs that are clearly onsite in a non-acceptable location. Check EARLY, save time."""


def _build_salary_section(profile: dict) -> str:
    """Build the salary negotiation instructions.

    Adapts floor, range, and currency from the profile's compensation section.
    """
    comp = profile["compensation"]
    currency = comp.get("salary_currency", "USD")
    floor = comp["salary_expectation"]
    range_min = comp.get("salary_range_min", floor)
    range_max = comp.get("salary_range_max", str(int(floor) + 20000) if floor.isdigit() else floor)
    conversion_note = comp.get("currency_conversion_note", "")

    # Compute example hourly rates at 3 salary levels
    try:
        floor_int = int(floor)
        examples = [
            (f"${floor_int // 1000}K", floor_int // 2080),
            (f"${(floor_int + 25000) // 1000}K", (floor_int + 25000) // 2080),
            (f"${(floor_int + 55000) // 1000}K", (floor_int + 55000) // 2080),
        ]
        hourly_line = ", ".join(f"{sal} = ${hr}/hr" for sal, hr in examples)
    except (ValueError, TypeError):
        hourly_line = "Divide annual salary by 2080"

    # Currency conversion guidance
    if conversion_note:
        convert_line = f"Posting is in a different currency? -> {conversion_note}"
    else:
        convert_line = "Posting is in a different currency? -> Target midpoint of their range. Convert if needed."

    return f"""== SALARY (think, don't just copy) ==
${floor} {currency} is the FLOOR. Never go below it. But don't always use it either.

Decision tree:
1. Job posting shows a range (e.g. "$120K-$160K")? -> Answer with the MIDPOINT ($140K).
2. Title says Senior, Staff, Lead, Principal, Architect, or level II/III/IV? -> Minimum $110K {currency}. Use midpoint of posted range if higher.
3. {convert_line}
4. No salary info anywhere? -> Use ${floor} {currency}.
5. Asked for a range? -> Give posted midpoint minus 10% to midpoint plus 10%. No posted range? -> "${range_min}-${range_max} {currency}".
6. Hourly rate? -> Divide your annual answer by 2080. ({hourly_line})"""


def _build_screening_section(profile: dict) -> str:
    """Build the screening questions guidance section."""
    personal = profile["personal"]
    exp = profile.get("experience", {})
    city = personal.get("city", "their city")
    years = exp.get("years_of_experience_total", "multiple")
    target_role = exp.get("target_role", personal.get("current_job_title", "software engineer"))
    work_auth = profile["work_authorization"]

    return f"""== SCREENING QUESTIONS (be strategic) ==
Hard facts -> answer truthfully from the profile. No guessing. This includes:
  - Location/relocation: lives in {city}, cannot relocate
  - Work authorization: {work_auth.get('legally_authorized_to_work', 'see profile')}
  - Citizenship, clearance, licenses, certifications: answer from profile only
  - Criminal/background: answer from profile only
  - Languages: ONLY claim proficiency in languages listed in the APPLICANT PROFILE above. If asked about ANY other language (German, Mandarin, Japanese, etc.), answer NO / Not proficient. Never fabricate language skills.

Skills and tools -> be confident about TECHNICAL skills. This candidate is a {target_role} with {years} years experience. If the question asks "Do you have experience with [tool]?" and it's in the same domain (DevOps, backend, ML, cloud, automation), answer YES. Software engineers learn tools fast. Don't sell short. But NEVER claim fluency in human languages not listed in the profile.

Open-ended questions ("Why do you want this role?", "Tell us about yourself", "What interests you?") -> Write 2-3 sentences. Be specific to THIS job. Reference something from the job description. Connect it to a real achievement from the resume. No generic fluff. No "I am passionate about..." -- sound like a real person.

EEO/demographics -> Use the values from APPLICANT PROFILE above (gender, race, veteran, disability). These are the candidate's actual preferences for disclosure."""


def _build_hard_rules(profile: dict) -> str:
    """Build the hard rules section with work auth and name from profile."""
    personal = profile["personal"]
    work_auth = profile["work_authorization"]

    full_name = personal["full_name"]
    preferred_name = personal.get("preferred_name", full_name.split()[0])
    preferred_last = full_name.split()[-1] if " " in full_name else ""
    display_name = f"{preferred_name} {preferred_last}".strip() if preferred_last else preferred_name

    # Build work auth rule dynamically
    auth_info = work_auth.get("legally_authorized_to_work", "")
    sponsorship = work_auth.get("require_sponsorship", "")
    permit_type = work_auth.get("work_permit_type", "")

    work_auth_rule = "Work auth: Answer truthfully from profile."
    if permit_type:
        work_auth_rule = f"Work auth: {permit_type}. Sponsorship needed: {sponsorship}."

    name_rule = f'Name: Legal name = {full_name}.'
    if preferred_name and preferred_name != full_name.split()[0]:
        name_rule += f' Preferred name = {preferred_name}. Use "{display_name}" unless a field specifically says "legal name".'

    return f"""== HARD RULES (never break these) ==
1. Never lie about: citizenship, work authorization, criminal history, education credentials, security clearance, licenses.
2. {work_auth_rule}
3. {name_rule}"""


def _build_site_credentials_section(site_credentials: dict) -> str:
    """Build the site-specific credentials block for the prompt.

    Args:
        site_credentials: Dict mapping domain -> {email, password}.

    Returns:
        Formatted credential lines for inclusion in step 5c.
    """
    if not site_credentials:
        return "       (No site-specific credentials configured.)"

    lines = ["       KNOWN CREDENTIALS (use these instead of default email/password):"]
    for domain, creds in site_credentials.items():
        email = creds.get("email", "")
        password = creds.get("password", "")
        lines.append(f"       - {domain}: email={email} / password={password}")
    return "\n".join(lines)


def _build_captcha_section() -> str:
    """Build the CAPTCHA detection and solving instructions.

    Reads the CapSolver API key from environment. The CAPTCHA section
    contains no personal data -- it's the same for every user.
    """
    config.load_env()
    capsolver_key = os.environ.get("CAPSOLVER_API_KEY", "")

    return f"""== CAPTCHA ==
You solve CAPTCHAs via the CapSolver REST API. No browser extension. You control the entire flow.
API key: {capsolver_key or 'NOT CONFIGURED — skip to MANUAL FALLBACK for all CAPTCHAs'}
API base: https://api.capsolver.com

CRITICAL RULE: When ANY CAPTCHA appears (hCaptcha, reCAPTCHA, Turnstile -- regardless of what it looks like visually), you MUST:
1. Run CAPTCHA DETECT to get the type and sitekey
2. Run CAPTCHA SOLVE (createTask -> poll -> inject) with the CapSolver API
3. ONLY go to MANUAL FALLBACK if CapSolver returns errorId > 0
Do NOT skip the API call based on what the CAPTCHA looks like. CapSolver solves CAPTCHAs server-side -- it does NOT need to see or interact with images, puzzles, or games. Even "drag the pipe" or "click all traffic lights" hCaptchas are solved via API token, not visually. ALWAYS try the API first.

--- CAPTCHA DETECT ---
Run this browser_evaluate after Apply/Submit/Login clicks, or when a page feels stuck. Do NOT run after every navigation — it triggers bot detection.
IMPORTANT: Detection order matters. hCaptcha elements also have data-sitekey, so check hCaptcha BEFORE reCAPTCHA.

browser_evaluate function: () => {{{{
  const r = {{}};
  const url = window.location.href;
  // 1. hCaptcha (check FIRST -- hCaptcha uses data-sitekey too)
  const hc = document.querySelector('.h-captcha, [data-hcaptcha-sitekey]');
  if (hc) {{{{
    r.type = 'hcaptcha'; r.sitekey = hc.dataset.sitekey || hc.dataset.hcaptchaSitekey;
  }}}}
  if (!r.type && document.querySelector('script[src*="hcaptcha.com"], iframe[src*="hcaptcha.com"]')) {{{{
    const el = document.querySelector('[data-sitekey]');
    if (el) {{{{ r.type = 'hcaptcha'; r.sitekey = el.dataset.sitekey; }}}}
  }}}}
  // 2. Cloudflare Turnstile
  if (!r.type) {{{{
    const cf = document.querySelector('.cf-turnstile, [data-turnstile-sitekey]');
    if (cf) {{{{
      r.type = 'turnstile'; r.sitekey = cf.dataset.sitekey || cf.dataset.turnstileSitekey;
      if (cf.dataset.action) r.action = cf.dataset.action;
      if (cf.dataset.cdata) r.cdata = cf.dataset.cdata;
    }}}}
  }}}}
  if (!r.type && document.querySelector('script[src*="challenges.cloudflare.com"]')) {{{{
    r.type = 'turnstile_script_only'; r.note = 'Wait 3s and re-detect.';
  }}}}
  // 3. reCAPTCHA v3 (invisible, loaded via render= param)
  if (!r.type) {{{{
    const s = document.querySelector('script[src*="recaptcha"][src*="render="]');
    if (s) {{{{
      const m = s.src.match(/render=([^&]+)/);
      if (m && m[1] !== 'explicit') {{{{ r.type = 'recaptchav3'; r.sitekey = m[1]; }}}}
    }}}}
  }}}}
  // 4. reCAPTCHA v2 (checkbox or invisible)
  if (!r.type) {{{{
    const rc = document.querySelector('.g-recaptcha');
    if (rc) {{{{ r.type = 'recaptchav2'; r.sitekey = rc.dataset.sitekey; }}}}
  }}}}
  if (!r.type && document.querySelector('script[src*="recaptcha"]')) {{{{
    const el = document.querySelector('[data-sitekey]');
    if (el) {{{{ r.type = 'recaptchav2'; r.sitekey = el.dataset.sitekey; }}}}
  }}}}
  // 5. FunCaptcha (Arkose Labs)
  if (!r.type) {{{{
    const fc = document.querySelector('#FunCaptcha, [data-pkey], .funcaptcha');
    if (fc) {{{{ r.type = 'funcaptcha'; r.sitekey = fc.dataset.pkey; }}}}
  }}}}
  if (!r.type && document.querySelector('script[src*="arkoselabs"], script[src*="funcaptcha"]')) {{{{
    const el = document.querySelector('[data-pkey]');
    if (el) {{{{ r.type = 'funcaptcha'; r.sitekey = el.dataset.pkey; }}}}
  }}}}
  if (r.type) {{{{ r.url = url; return r; }}}}
  return null;
}}}}

Result actions:
- null -> no CAPTCHA. Continue normally.
- "turnstile_script_only" -> browser_wait_for time: 3, re-run detect.
- Any other type -> proceed to CAPTCHA SOLVE below.

--- CAPTCHA SOLVE ---
Three steps: createTask -> poll -> inject. Do each as a separate browser_evaluate call.

STEP 1 -- CREATE TASK (copy this exactly, fill in the 3 placeholders):
browser_evaluate function: async () => {{{{
  const r = await fetch('https://api.capsolver.com/createTask', {{{{
    method: 'POST',
    headers: {{{{'Content-Type': 'application/json'}}}},
    body: JSON.stringify({{{{
      clientKey: '{capsolver_key}',
      task: {{{{
        type: 'TASK_TYPE',
        websiteURL: 'PAGE_URL',
        websiteKey: 'SITE_KEY'
      }}}}
    }}}})
  }}}});
  return await r.json();
}}}}

TASK_TYPE values (use EXACTLY these strings):
  hcaptcha     -> HCaptchaTaskProxyLess
  recaptchav2  -> ReCaptchaV2TaskProxyLess
  recaptchav3  -> ReCaptchaV3TaskProxyLess
  turnstile    -> AntiTurnstileTaskProxyLess
  funcaptcha   -> FunCaptchaTaskProxyLess

PAGE_URL = the url from detect result. SITE_KEY = the sitekey from detect result.
For recaptchav3: add "pageAction": "submit" to the task object (or the actual action found in page scripts).
For turnstile: add "metadata": {{"action": "...", "cdata": "..."}} if those were in detect result.

Response: {{"errorId": 0, "taskId": "abc123"}} on success.
If errorId > 0 -> CAPTCHA SOLVE failed. Go to MANUAL FALLBACK.

STEP 2 -- POLL (replace TASK_ID with the taskId from step 1):
Loop: browser_wait_for time: 3, then run:
browser_evaluate function: async () => {{{{
  const r = await fetch('https://api.capsolver.com/getTaskResult', {{{{
    method: 'POST',
    headers: {{{{'Content-Type': 'application/json'}}}},
    body: JSON.stringify({{{{
      clientKey: '{capsolver_key}',
      taskId: 'TASK_ID'
    }}}})
  }}}});
  return await r.json();
}}}}

- status "processing" -> wait 3s, poll again. Max 10 polls (30s).
- status "ready" -> extract token:
    reCAPTCHA: solution.gRecaptchaResponse
    hCaptcha:  solution.gRecaptchaResponse
    Turnstile: solution.token
- errorId > 0 or 30s timeout -> MANUAL FALLBACK.

STEP 3 -- INJECT TOKEN (replace THE_TOKEN with actual token string):

For reCAPTCHA v2/v3:
browser_evaluate function: () => {{{{
  const token = 'THE_TOKEN';
  document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {{{{ el.value = token; el.style.display = 'block'; }}}});
  if (window.___grecaptcha_cfg) {{{{
    const clients = window.___grecaptcha_cfg.clients;
    for (const key in clients) {{{{
      const walk = (obj, d) => {{{{
        if (d > 4 || !obj) return;
        for (const k in obj) {{{{
          if (typeof obj[k] === 'function' && k.length < 3) try {{{{ obj[k](token); }}}} catch(e) {{{{}}}}
          else if (typeof obj[k] === 'object') walk(obj[k], d+1);
        }}}}
      }}}};
      walk(clients[key], 0);
    }}}}
  }}}}
  return 'injected';
}}}}

For hCaptcha:
browser_evaluate function: () => {{{{
  const token = 'THE_TOKEN';
  const ta = document.querySelector('[name="h-captcha-response"], textarea[name*="hcaptcha"]');
  if (ta) ta.value = token;
  document.querySelectorAll('iframe[data-hcaptcha-response]').forEach(f => f.setAttribute('data-hcaptcha-response', token));
  const cb = document.querySelector('[data-hcaptcha-widget-id]');
  if (cb && window.hcaptcha) try {{{{ window.hcaptcha.getResponse(cb.dataset.hcaptchaWidgetId); }}}} catch(e) {{{{}}}}
  return 'injected';
}}}}

For Turnstile:
browser_evaluate function: () => {{{{
  const token = 'THE_TOKEN';
  const inp = document.querySelector('[name="cf-turnstile-response"], input[name*="turnstile"]');
  if (inp) inp.value = token;
  if (window.turnstile) try {{{{ const w = document.querySelector('.cf-turnstile'); if (w) window.turnstile.getResponse(w); }}}} catch(e) {{{{}}}}
  return 'injected';
}}}}

For FunCaptcha:
browser_evaluate function: () => {{{{
  const token = 'THE_TOKEN';
  const inp = document.querySelector('#FunCaptcha-Token, input[name="fc-token"]');
  if (inp) inp.value = token;
  if (window.ArkoseEnforcement) try {{{{ window.ArkoseEnforcement.setConfig({{{{data: {{{{blob: token}}}}}}}}) }}}} catch(e) {{{{}}}}
  return 'injected';
}}}}

After injecting: browser_wait_for time: 2, then snapshot.
- Widget gone or green check -> success. Click Submit if needed.
- No change -> click Submit/Verify/Continue button (some sites need it).
- Still stuck -> token may have expired (~2 min lifetime). Re-run from STEP 1.

--- MANUAL FALLBACK ---
You should ONLY be here if CapSolver createTask returned errorId > 0. If you haven't tried CapSolver yet, GO BACK and try it first.
If CapSolver genuinely failed (errorId > 0):
1. Audio challenge: Look for "audio" or "accessibility" button -> click it for an easier challenge.
2. Text/logic puzzles: Solve them yourself. Think step by step. Common tricks: "All but 9 die" = 9 left. "3 sisters and 4 brothers, how many siblings?" = 7.
3. Simple text captchas ("What is 3+7?", "Type the word") -> solve them.
4. All else fails -> Output RESULT:CAPTCHA."""


def _build_qa_section() -> str:
    """Build the known Q&A pairs section for the agent prompt.

    Queries the qa_knowledge table and formats accepted/human-provided answers
    so the agent can reuse them for screening questions.
    """
    all_qa = get_all_qa()
    if not all_qa:
        return ""

    # Prioritize: human answers first, then accepted agent answers, then others
    priority = {"human": 0, "profile": 1, "agent": 2}
    # Group by question_key, pick best answer per question
    best: dict[str, dict] = {}
    for qa in all_qa:
        key = qa["question_key"]
        existing = best.get(key)
        if existing is None:
            best[key] = qa
            continue
        # Prefer accepted outcome
        if qa["outcome"] == "accepted" and existing["outcome"] != "accepted":
            best[key] = qa
            continue
        # Prefer human/profile source
        if priority.get(qa["answer_source"], 3) < priority.get(existing["answer_source"], 3):
            best[key] = qa

    if not best:
        return ""

    lines = ["== KNOWN SCREENING ANSWERS (use these when you encounter matching questions) =="]
    for qa in best.values():
        outcome_tag = f" [{qa['outcome']}, source: {qa['answer_source']}]" if qa["outcome"] != "unknown" else f" [source: {qa['answer_source']}]"
        lines.append(f'Q: "{qa["question_text"]}" → A: "{qa["answer_text"]}"{outcome_tag}')

    lines.append("")
    lines.append("If a screening question closely matches one above, use the known answer.")
    return "\n".join(lines)


def build_prompt(job: dict, tailored_resume: str,
                 cover_letter: str | None = None,
                 dry_run: bool = False) -> str:
    """Build the full instruction prompt for the apply agent.

    Loads the user profile and search config internally. All personal data
    comes from the profile -- nothing is hardcoded.

    Args:
        job: Job dict from the database (must have url, title, site,
             application_url, fit_score, tailored_resume_path).
        tailored_resume: Plain-text content of the tailored resume.
        cover_letter: Optional plain-text cover letter content.
        dry_run: If True, tell the agent not to click Submit.

    Returns:
        Complete prompt string for the AI agent.
    """
    profile = config.load_profile()
    search_config = config.load_search_config()
    personal = profile["personal"]

    # --- Resolve resume PDF path ---
    resume_path = job.get("tailored_resume_path")
    if not resume_path:
        raise ValueError(f"No tailored resume for job: {job.get('title', 'unknown')}")

    src_pdf = Path(resume_path).with_suffix(".pdf").resolve()
    if not src_pdf.exists():
        raise ValueError(f"Resume PDF not found: {src_pdf}")

    # Copy to a clean filename for upload (recruiters see the filename)
    full_name = personal["full_name"]
    name_slug = full_name.replace(" ", "_")
    dest_dir = config.APPLY_WORKER_DIR / "current"
    dest_dir.mkdir(parents=True, exist_ok=True)
    upload_pdf = dest_dir / f"{name_slug}_Resume.pdf"
    shutil.copy(str(src_pdf), str(upload_pdf))
    pdf_path = str(upload_pdf)

    # --- Cover letter handling ---
    cover_letter_text = cover_letter or ""
    cl_upload_path = ""
    cl_path = job.get("cover_letter_path")
    if cl_path and Path(cl_path).exists():
        cl_src = Path(cl_path)
        # Read text from .txt sibling (PDF is binary)
        cl_txt = cl_src.with_suffix(".txt")
        if cl_txt.exists():
            cover_letter_text = cl_txt.read_text(encoding="utf-8")
        elif cl_src.suffix == ".txt":
            cover_letter_text = cl_src.read_text(encoding="utf-8")
        # Upload must be PDF
        cl_pdf_src = cl_src.with_suffix(".pdf")
        if cl_pdf_src.exists():
            cl_upload = dest_dir / f"{name_slug}_Cover_Letter.pdf"
            shutil.copy(str(cl_pdf_src), str(cl_upload))
            cl_upload_path = str(cl_upload)

    # --- Build all prompt sections ---
    profile_summary = _build_profile_summary(profile)
    location_check = _build_location_check(profile, search_config)
    salary_section = _build_salary_section(profile)
    screening_section = _build_screening_section(profile)
    hard_rules = _build_hard_rules(profile)
    captcha_section = _build_captcha_section()
    qa_section = _build_qa_section()

    # Cover letter fallback text
    city = personal.get("city", "the area")
    if not cover_letter_text:
        cl_display = (
            f"None available. Skip if optional. If required, write 2 factual "
            f"sentences: (1) relevant experience from the resume that matches "
            f"this role, (2) available immediately and based in {city}."
        )
    else:
        cl_display = cover_letter_text

    # Phone digits only (for fields with country prefix)
    phone_digits = "".join(c for c in personal.get("phone", "") if c.isdigit())

    # SSO domains the agent cannot sign into (loaded from config/sites.yaml)
    from applypilot.config import load_blocked_sso, load_no_signup_domains
    blocked_sso = load_blocked_sso()
    no_signup_domains = load_no_signup_domains()

    # Site-specific credentials (e.g. LinkedIn uses a different email than apply email)
    # DB accounts as base, profile.json overrides
    from applypilot.database import get_accounts_for_prompt
    site_credentials = get_accounts_for_prompt()
    site_credentials.update(profile.get("site_credentials", {}))

    # Preferred display name
    preferred_name = personal.get("preferred_name", full_name.split()[0])
    last_name = full_name.split()[-1] if " " in full_name else ""
    display_name = f"{preferred_name} {last_name}".strip()

    # Dry-run: override submit instruction
    if dry_run:
        submit_instruction = "IMPORTANT: Do NOT click the final Submit/Apply button. Review the form, verify all fields, then output RESULT:APPLIED with a note that this was a dry run."
    else:
        submit_instruction = "BEFORE clicking Submit/Apply, take a snapshot and review EVERY field on the page. Verify all data matches the APPLICANT PROFILE and TAILORED RESUME -- name, email, phone, location, work auth, resume uploaded, cover letter if applicable. If anything is wrong or missing, fix it FIRST. Only click Submit after confirming everything is correct."

    prompt = f"""You are an autonomous job application agent. Your ONE mission: get this candidate an interview. You have all the information and tools. Think strategically. Act decisively. Submit the application.

IMPORTANT: You are running on a REAL computer with FULL filesystem access. You are NOT in a sandbox. You CAN read/write files, upload documents, and access the local filesystem. The resume and cover letter paths below are real files on disk — use them directly.

== JOB ==
URL: {job.get('application_url') or job['url']}
Title: {job['title']}
Company: {job.get('site', 'Unknown')}
Fit Score: {job.get('fit_score', 'N/A')}/10

== FILES ==
Resume PDF (upload this): {pdf_path}
Cover Letter PDF (upload if asked): {cl_upload_path or "N/A"}

== RESUME TEXT (use when filling text fields) ==
{tailored_resume}

== COVER LETTER TEXT (paste if text field, upload PDF if file field) ==
{cl_display}

== APPLICANT PROFILE ==
{profile_summary}

== YOUR MISSION ==
Submit a complete, accurate application. Use the profile and resume as source data -- adapt to fit each form's format.

If something unexpected happens and these instructions don't cover it, figure it out yourself. You are autonomous. Navigate pages, read content, try buttons, explore the site. The goal is always the same: submit the application. Do whatever it takes to reach that goal.

{hard_rules}

== NEVER DO THESE (immediate RESULT:FAILED if encountered) ==
- NEVER grant camera, microphone, screen sharing, or location permissions. If a site requests them -> RESULT:FAILED:unsafe_permissions
- NEVER do video/audio verification, selfie capture, ID photo upload, or biometric anything -> RESULT:FAILED:unsafe_verification
- NEVER set up a freelancing profile (Mercor, Toptal, Upwork, Fiverr, Turing, etc.). These are contractor marketplaces, not job applications -> RESULT:FAILED:not_a_job_application
- NEVER agree to hourly/contract rates, availability calendars, or "set your rate" flows. You are applying for FULL-TIME salaried positions only. If the posting is contract/hourly-only -> RESULT:FAILED:contract_only
- NEVER install browser extensions, download executables, or run assessment software.
- NEVER enter payment info, bank details, or SSN/SIN.
- NEVER click "Allow" on any browser permission popup. Always deny/block.
- If the site is NOT a job application form (it's a profile builder, skills marketplace, talent network signup, coding assessment platform) -> RESULT:FAILED:not_a_job_application

{location_check}

{salary_section}

{screening_section}

{qa_section}

== Q&A LOGGING (output after each screening question you answer) ==
After answering each screening question on the application form, output this line:
QA:{{exact question text}}|{{your answer}}|{{field_type}}
Where field_type is one of: text, select, radio, checkbox, textarea
Example: QA:Are you authorized to work in the US?|Yes|radio
Example: QA:How did you hear about us?|Online Job Board|select
This helps us build a knowledge base for future applications.

== SCREENING QUESTION ESCALATION ==
If you encounter screening questions that you CANNOT answer from the APPLICANT PROFILE
or KNOWN SCREENING ANSWERS, and they are REQUIRED (no skip option), output EACH unknown
question on its own line BEFORE outputting the NEEDS_HUMAN result:

SCREENING_Q:{{exact question text}}|{{field_type}}|{{comma-separated options if select/radio, empty otherwise}}

Example:
SCREENING_Q:Do you have experience with SAP HANA?|radio|Yes,No
SCREENING_Q:Describe your experience with supply chain management|textarea|

Then output RESULT:NEEDS_HUMAN:screening_questions:{{current_page_url}}

The pipeline operator will provide answers. The agent will be relaunched with your answers
in the KNOWN SCREENING ANSWERS section. The form will still be open in the browser.

== STEP-BY-STEP ==
1. browser_navigate to the job URL.
1a. LINKEDIN LANGUAGE CHECK (LinkedIn URLs only — skip for all other sites):
   After navigating to any linkedin.com page, take a browser_snapshot. If the UI is NOT in English
   (e.g., you see "Postuler", "Bewerben", "Candidatar", "Следующий", or any non-English button labels
   on the job page), fix it BEFORE continuing:
   - browser_evaluate: `window.scrollTo(0, document.body.scrollHeight)` to scroll to the page bottom.
   - browser_snapshot: find the language selector button/link near the bottom footer (it shows the
     current language name, e.g. "Français", "Deutsch").
   - Click that language selector to open the dropdown.
   - browser_snapshot: find "English" in the list and click it.
   - Wait 2 seconds for the page to reload in English.
   - browser_snapshot to confirm the page is now in English before continuing to step 2.
   If the page is already in English, skip this step entirely.
2. browser_snapshot to read the page. Then run CAPTCHA DETECT (see CAPTCHA section). If a CAPTCHA is found, solve it before continuing.
3. LOCATION CHECK. Read the page for location info. If not eligible, output RESULT and stop.
4. Find and click the Apply button. If email-only (page says "email resume to X"):
   - send_email with subject "Application for {job['title']} -- {display_name}", body = 2-3 sentence pitch + contact info, attach resume PDF: ["{pdf_path}"]
   - Output RESULT:APPLIED. Done.
   After clicking Apply: browser_snapshot. Run CAPTCHA DETECT -- many sites trigger CAPTCHAs right after the Apply click. If found, solve before continuing.
5. Login wall?
   5a. FIRST: check the URL. If you landed on {', '.join(blocked_sso)}, or any SSO/OAuth page -> STOP. Output RESULT:FAILED:sso_required. Do NOT try to sign in to Google/Microsoft/SSO.
   5b. SOCIAL LOGIN SHORTCUT: Before using email/password, look for a "Sign in with LinkedIn", "Apply with LinkedIn", or LinkedIn logo button on the login page. If present:
     - Click the LinkedIn button.
     - If a LinkedIn OAuth popup opens, use browser_tabs action "list" then "select" to switch to it.
     - If LinkedIn asks you to authorize the app, click Allow/Authorize.
     - Switch back to the main application tab.
     - LinkedIn login often pre-fills the entire application form — verify the pre-filled data against the APPLICANT PROFILE and fix mismatches.
     - If LinkedIn login fails (wrong account, no active session, error), fall back to email/password login below.
     - Do NOT use this on LinkedIn.com itself — it's a no-signup domain.
     - Do NOT confuse this with Google/Microsoft SSO — those are still blocked per 5a.
   5c. Check for popups. Run browser_tabs action "list". If a new tab/window appeared (login popup), switch to it with browser_tabs action "select". Check the URL there too -- if it's SSO -> RESULT:FAILED:sso_required.
   5d. Check if the site matches a KNOWN CREDENTIAL below. If yes, use those credentials. Otherwise use default: {personal['email']} / {personal.get('password', '')}
{_build_site_credentials_section(site_credentials)}
   5e. After clicking Login/Sign-in: run CAPTCHA DETECT. Login pages frequently have invisible CAPTCHAs that silently block form submissions. If found, solve it then retry login.
   5f. Sign in failed? Check if the current site's domain matches ANY of these NO-SIGNUP domains: {', '.join(no_signup_domains)}. If YES -> NEVER create an account. Output RESULT:FAILED:login_required immediately. The user will log in manually in the Chrome worker window, then retry.
   5g. NOT a no-signup domain (i.e. it's an employer/ATS site like Workday, iCIMS, etc.)? Sign up IS allowed. Use email {personal['email']}. Generate a RANDOM 16-character password (mix of upper, lower, digits, symbols). After successful signup, output this line EXACTLY (JSON format):
       ACCOUNT_CREATED:{{"site":"<company name>","email":"{personal['email']}","password":"<the generated password>","domain":"<site domain>"}}
   5h. Need email verification (code or link)?
       CRITICAL: You MUST attempt Gmail MCP search_emails at least 3 times before giving up.
       If the page says "check your email", "verification code sent", "verify your email", or
       anything about an email/code being sent — this IS email verification. Use Gmail MCP. NOW.
       DO NOT output RESULT:NEEDS_HUMAN until you have exhausted ALL Gmail MCP attempts below.
       - Wait 5 seconds for the email to arrive.
       - Attempt 1: search_emails with query "to:{personal['email']} subject:(verification OR verify OR confirm OR code OR activate) newer_than:2m". ALWAYS include to:{personal['email']} to filter out personal mail.
       - If no results, wait 10 more seconds.
       - Attempt 2: search_emails with a broader query, e.g. "to:{personal['email']} newer_than:2m" (or add the site domain, e.g. "to:{personal['email']} from:greenhouse.io newer_than:2m").
       - If still no results, wait 10 more seconds.
       - Attempt 3: search_emails with "to:{personal['email']} in:spam newer_than:5m" (check spam/junk).
       - read_email to get the full message body. Extract the 4-8 digit code or the verification link.
       - If it's a code: type it into the verification field and submit.
       - If it's a link: browser_navigate to the link, then switch back to the application tab.
       - If no email arrives after all 3 attempts (~30s total): output RESULT:NEEDS_HUMAN:sms_verification:{{current_page_url}} — but ONLY if you have genuinely tried Gmail MCP 3 times.
       - SMS/text verification: You CANNOT receive SMS codes. If the site ONLY offers phone/SMS verification with NO email option visible, output RESULT:NEEDS_HUMAN:sms_verification:{{current_page_url}} immediately.
   5i. After login, run browser_tabs action "list" again. Switch back to the application tab if needed.
   5j. All failed? Output RESULT:FAILED:login_issue. Do not loop.
6. Upload resume. ALWAYS upload fresh -- delete any existing resume first, then browser_file_upload with the PDF path above. This is the tailored resume for THIS job. Non-negotiable.
7. Upload cover letter if there's a field for it. Text field -> paste the cover letter text. File upload -> use the cover letter PDF path.
8. Check ALL pre-filled fields. ATS systems parse your resume and auto-fill -- it's often WRONG.
   - "Current Job Title" or "Most Recent Title" -> use the title from the TAILORED RESUME summary, NOT whatever the parser guessed.
   - Compare every other field to the APPLICANT PROFILE. Fix mismatches. Fill empty fields.
9. Answer screening questions using the rules above.
10. {submit_instruction}
11. After submit: browser_snapshot. Run CAPTCHA DETECT -- submit buttons often trigger invisible CAPTCHAs. If found, solve it (the form will auto-submit once the token clears, or you may need to click Submit again). Then check for new tabs (browser_tabs action: "list"). Switch to newest, close old. Snapshot to confirm submission. Look for "thank you" or "application received".
12. Output your result.

== CRITICAL: YOU MUST OUTPUT A RESULT CODE ==
Your VERY LAST message MUST contain exactly one RESULT: line from below. This is NON-NEGOTIABLE. Every response you give MUST end with a RESULT line. If you submitted the form, output RESULT:APPLIED. If something went wrong, output the appropriate RESULT:FAILED:reason. If you are about to summarize your work or give a recommendation, you STILL must end with a RESULT line. NEVER end without a RESULT line — doing so is a bug in YOUR behavior.

== RESULT CODES (output EXACTLY one) ==
RESULT:APPLIED -- submitted successfully
RESULT:EXPIRED -- job closed or no longer accepting applications
RESULT:CAPTCHA -- blocked by unsolvable captcha
RESULT:LOGIN_ISSUE -- could not sign in or create account
RESULT:NEEDS_HUMAN:workday_signup:{{url}} -- Workday "Create Account" page; output the current page URL as {{url}}
RESULT:NEEDS_HUMAN:login_required:{{url}} -- Login failed twice on a non-SSO site; output the current page URL as {{url}}
RESULT:NEEDS_HUMAN:sms_verification:{{url}} -- Phone/SMS-only verification required (you already tried Gmail MCP 3 times and confirmed no email option); output the current page URL as {{url}}
RESULT:NEEDS_HUMAN:form_stuck:{{url}} -- Form partially filled but stuck on a field/dropdown/validation error after 3 attempts. User should complete and submit manually.
RESULT:NEEDS_HUMAN:screening_questions:{{url}} -- Screening questions require answers not in the profile (e.g., niche tool experience, immigration details, essay questions). User should answer them.
RESULT:FAILED:not_eligible_location -- onsite outside acceptable area, no remote option
RESULT:FAILED:not_eligible_work_auth -- requires unauthorized work location
RESULT:FAILED:sso_required -- site requires SSO/OAuth login (Google/Microsoft); user cannot fix this
RESULT:FAILED:reason -- any other failure (brief reason)

== BROWSER EFFICIENCY ==
- browser_snapshot ONCE per page to understand it. Then use browser_take_screenshot to check results (10x less memory).
- Only snapshot again when you need element refs to click/fill.
- Multi-page forms (Workday, Taleo, iCIMS): snapshot each new page, fill all fields, click Next/Continue. Repeat until final review page.
- Fill ALL fields in ONE browser_fill_form call. Not one at a time.
- Keep your thinking SHORT. Don't repeat page structure back.
== ANTI-BOT BEHAVIOR (follow these to avoid detection) ==
- PACING: Add browser_wait_for time: 1 between ALL interactions (fill, click, navigate). Rapid-fire actions trigger bot detection on iCIMS and similar platforms. Human pace = fewer CAPTCHAs.
- HOVER-BEFORE-CLICK: For important buttons (Submit, Apply, Next, Continue, Sign In), always browser_hover the element first, then browser_wait_for time: 1, then browser_click. This mimics natural mouse movement and defeats hover-based bot detectors.
- SCROLL-INTO-VIEW: Before clicking an element that may be below the fold, scroll it into view first with browser_evaluate: `() => {{{{ document.querySelector('SELECTOR')?.scrollIntoView({{{{behavior: 'smooth', block: 'center'}}}}); }}}}` — then wait 1s before clicking.
- FILE UPLOAD WAIT: After every browser_file_upload, add browser_wait_for time: 2 to let the ATS parse the uploaded file before continuing. Many ATSes (Workday, Greenhouse) auto-fill form fields from the resume — rushing past this causes blank fields.
- CAPTCHA AWARENESS: After Apply/Submit/Login clicks, or when a page feels stuck/unresponsive -- run CAPTCHA DETECT (see CAPTCHA section). Do NOT run it after every single navigation — excessive JS evaluation triggers bot detection. Invisible CAPTCHAs (Turnstile, reCAPTCHA v3) show NO visual widget but block form submissions silently. The detect script finds them even when invisible.

== FORM TRICKS ==
- Popup/new window opened? browser_tabs action "list" to see all tabs. browser_tabs action "select" with the tab index to switch. ALWAYS check for new tabs after clicking login/apply/sign-in buttons.
- "Upload your resume" pre-fill page (Workday, Lever, etc.): This is NOT the application form yet. Click "Select file" or the upload area, then browser_file_upload with the resume PDF path. Wait for parsing to finish. Then click Next/Continue to reach the actual form.
- File upload not working? Try: (1) browser_click the upload button/area, (2) browser_file_upload with the path. If still failing, look for a hidden file input or a "Select file" link and click that first.
- Dropdown won't fill? browser_click to open it, then browser_click the option.
- REACT DROPDOWNS (Greenhouse, NerdWallet, most modern ATS): NEVER use browser_select_option on React-controlled <select> elements — it sets the DOM value but doesn't fire React's synthetic onChange, so the form shows validation errors on submit even though the field looks filled. Instead: (1) browser_click the dropdown/select element to focus it, (2) browser_snapshot to see if a custom listbox appeared, (3) if a listbox appeared: browser_click the desired option in it; if no listbox: use browser_evaluate to dispatch a real React change event:
  browser_evaluate function: () => {{ const sel = document.querySelector('select[name="..."]'); const nativeSet = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; nativeSet.call(sel, 'VALUE'); sel.dispatchEvent(new Event('change', {{bubbles: true}})); return sel.value; }}
  After filling all dropdowns, do a browser_snapshot before clicking Submit to verify values are retained.
- iCIMS FORMS (careers-*.icims.com): These use custom dropdown widgets, NOT native <select> elements. browser_select_option WILL FAIL — never use it on iCIMS.
  Strategy: (1) browser_click the dropdown to open it, (2) if a search/filter field appears, type your search text, (3) browser_wait_for time: 1, (4) browser_snapshot to see available options, (5) browser_click the specific option.
  If the desired option (e.g., "Other") is not visible in the dropdown list, the listbox is virtualized — scroll it first:
  browser_evaluate function: () => {{ const lb = document.querySelector('[role="listbox"]'); if (lb) {{ lb.scrollTop = lb.scrollHeight; }} return 'scrolled'; }}
  Then snapshot again and click the option. Repeat scroll+snapshot if still not visible.
  iCIMS forms have 3 steps. Snapshot each step, fill all fields, click Next/Submit.
  If auto-filled data from resume parsing is WRONG (common on iCIMS), clear it and re-enter from the APPLICANT PROFILE.
  iCIMS LOGIN: Look for "Sign in with LinkedIn" on the login page — iCIMS widely supports LinkedIn OAuth and it's faster than email/password. Use the SOCIAL LOGIN SHORTCUT (step 5b) first.
- Checkbox won't check via fill_form? Use browser_click on it instead. Snapshot to verify.
- Phone field with country prefix: just type digits {phone_digits}
- Date fields: {datetime.now().strftime('%m/%d/%Y')}
- Validation errors after submit? Take BOTH snapshot AND screenshot. Snapshot shows text errors, screenshot shows red-highlighted fields. Fix all, retry.
- Honeypot fields (hidden, "leave blank"): skip them.
- Format-sensitive fields: read the placeholder text, match it exactly.

{captcha_section}

== WHEN TO GIVE UP ==
- Same page after 3 attempts with no progress, form has data entered -> RESULT:NEEDS_HUMAN:form_stuck:{{current_page_url}} (user finishes it)
- Same page after 3 attempts, form is empty/blank/broken -> RESULT:FAILED:stuck
- Screening questions you cannot confidently answer from the APPLICANT PROFILE or KNOWN SCREENING ANSWERS, and they appear to be required with no "skip" option -> RESULT:NEEDS_HUMAN:screening_questions:{{current_page_url}}
- Job is closed/expired/page says "no longer accepting" -> RESULT:EXPIRED
- Page is broken/500 error/blank -> RESULT:FAILED:page_error
- Workday subdomain (*.myworkdayjobs.com) shows "Create Account" / "Sign Up" with no existing-account login option -> RESULT:NEEDS_HUMAN:workday_signup:{{current_page_url}}
- Login failed twice on a non-SSO employer/ATS site (NOT LinkedIn/Indeed/etc.) -> RESULT:NEEDS_HUMAN:login_required:{{current_page_url}}
- SMS or phone number verification required, no email code option (and you already tried Gmail MCP 3 times) -> RESULT:NEEDS_HUMAN:sms_verification:{{current_page_url}}
Stop immediately. Output your RESULT code. Do not loop."""

    return prompt
