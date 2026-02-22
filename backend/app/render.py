from __future__ import annotations

from typing import Iterable, List

from .resume_schema import Resume


LATEX_REPLACEMENTS = {
	"&": "\\&",
	"%": "\\%",
	"$": "\\$",
	"#": "\\#",
	"_": "\\_",
	"{": "\\{",
	"}": "\\}",
	"~": "\\textasciitilde{}",
	"^": "\\textasciicircum{}",
	"\\": "\\textbackslash{}",
}


def _escape_latex(text: str) -> str:
	if not text:
		return ""
	escaped = text.replace("\\", LATEX_REPLACEMENTS["\\"])
	for key, value in LATEX_REPLACEMENTS.items():
		if key == "\\":
			continue
		escaped = escaped.replace(key, value)
	return escaped


def _normalize_url(url: str) -> str:
	if not url:
		return ""
	if url.startswith("http://") or url.startswith("https://"):
		return url
	return f"https://{url}"


def _join_non_empty(parts: Iterable[str], sep: str = " \\quad ") -> str:
	cleaned = [part for part in parts if part]
	return sep.join(cleaned)


def _format_itemize(items: List[str]) -> str:
	cleaned = [_escape_latex(item) for item in items if item.strip()]
	if not cleaned:
		return ""
	lines = ["\\begin{itemize}"]
	lines.extend([f"    \\item {item}" for item in cleaned])
	lines.append("\\end{itemize}")
	return "\n".join(lines)


def _gpa_should_show(gpa: str) -> bool:
	if not gpa:
		return False
	try:
		return float(gpa) >= 3.5
	except ValueError:
		return True


def _section(title: str, body: str) -> str:
	body = body.strip()
	if not body:
		return ""
	return f"\\section*{{{_escape_latex(title)}}}\n{body}\n"


def _render_header(resume: Resume) -> str:
	header = resume.header
	name = _escape_latex(header.name) if header.name else ""
	contact_parts: List[str] = []

	if header.phone:
		contact_parts.append(_escape_latex(header.phone))
	if header.email:
		email = _escape_latex(header.email)
		contact_parts.append(f"\\href{{mailto:{header.email}}}{{{email}}}")
	if header.linkedin:
		link = _normalize_url(header.linkedin)
		contact_parts.append(f"\\href{{{link}}}{{{_escape_latex(header.linkedin)}}}")
	if header.github:
		link = _normalize_url(header.github)
		contact_parts.append(f"\\href{{{link}}}{{{_escape_latex(header.github)}}}")
	if header.portfolio:
		link = _normalize_url(header.portfolio)
		contact_parts.append(f"\\href{{{link}}}{{{_escape_latex(header.portfolio)}}}")
	if header.location:
		contact_parts.append(_escape_latex(header.location))

	contact_line = _join_non_empty(contact_parts)
	lines = ["\\begin{center}"]
	if name:
		lines.append(f"    {{\\LARGE \\textbf{{{name}}}}} \\")
	if contact_line:
		lines.append(f"    {contact_line}")
	lines.append("\\end{center}")
	return "\n".join(lines)


def _render_education(resume: Resume) -> str:
	entries = []
	for edu in resume.education:
		school = _escape_latex(edu.school)
		degree_bits = " ".join(
			part for part in [_escape_latex(edu.degree), _escape_latex(edu.major)] if part
		)
		grad = _escape_latex(edu.grad)
		lines = []
		header = _join_non_empty([
			f"\\textbf{{{school}}}" if school else "",
			f"\\hfill {grad}" if grad else "",
		], sep=" ")
		if header:
			lines.append(header + " \\")
		if degree_bits:
			lines.append(degree_bits + " \\")
		if edu.coursework:
			coursework = ", ".join(_escape_latex(cw) for cw in edu.coursework if cw.strip())
			if coursework:
				lines.append(f"\\textbf{{Coursework:}} {coursework}")
		if _gpa_should_show(edu.gpa):
			lines.append(f"GPA: {_escape_latex(edu.gpa)}")
		if lines:
			entries.append("\n".join(lines))
	return _section("Education", "\n\n".join(entries))


def _render_experience(resume: Resume) -> str:
	entries = []
	for role in resume.experience:
		company = _escape_latex(role.company)
		location = _escape_latex(role.location)
		date_range = _join_non_empty([_escape_latex(role.start), _escape_latex(role.end)], sep=" -- ")
		left_bits = []
		if company:
			left_bits.append(f"\\textbf{{{company}}}")
		if location:
			left_bits.append(f"\\textit{{{location}}}")
		left_text = " ".join(left_bits)
		header = _join_non_empty([
			left_text,
			f"\\hfill {date_range}" if date_range else "",
		], sep=" ")
		role_line = _escape_latex(role.role)
		bullets = _format_itemize(role.bullets)
		parts = []
		if header:
			parts.append(header + " \\")
		if role_line:
			parts.append(role_line)
		if bullets:
			parts.append(bullets)
		if parts:
			entries.append("\n".join(parts))
	return _section("Work Experience", "\n\n".join(entries))


def _render_projects(resume: Resume) -> str:
	entries = []
	for project in resume.projects:
		name = _escape_latex(project.name)
		link = _normalize_url(project.link) if project.link else ""
		header = f"\\textbf{{{name}}}" if name else ""
		if link:
			header = _join_non_empty([header, f"\\href{{{link}}}{{{_escape_latex(project.link)}}}"], sep=" \\textemdash ")
		date_range = _join_non_empty([_escape_latex(project.start), _escape_latex(project.end)], sep=" -- ")
		if date_range:
			header = _join_non_empty([header, f"\\hfill {date_range}"], sep=" ")
		stack = ", ".join(_escape_latex(item) for item in project.stack if item.strip())
		bullets = _format_itemize(project.bullets)
		parts = []
		if header:
			parts.append(header + " \\")
		if stack:
			parts.append(f"\\textit{{Stack:}} {stack}")
		if bullets:
			parts.append(bullets)
		if parts:
			entries.append("\n".join(parts))
	return _section("Projects", "\n\n".join(entries))


def _render_skills(resume: Resume) -> str:
	skills = resume.skills
	lines = []
	if skills.languages:
		lines.append(f"\\textbf{{Programming Languages:}} {', '.join(_escape_latex(s) for s in skills.languages)}")
	if skills.frameworks:
		lines.append(f"\\textbf{{Frameworks:}} {', '.join(_escape_latex(s) for s in skills.frameworks)}")
	if skills.tools:
		lines.append(f"\\textbf{{Tools:}} {', '.join(_escape_latex(s) for s in skills.tools)}")
	if skills.concepts:
		lines.append(f"\\textbf{{Concepts:}} {', '.join(_escape_latex(s) for s in skills.concepts)}")
	return _section("Skills", "\\\\\n".join(lines))


def _render_leadership(resume: Resume) -> str:
	entries = []
	for leader in resume.leadership:
		org = _escape_latex(leader.org)
		date_range = _join_non_empty([_escape_latex(leader.start), _escape_latex(leader.end)], sep=" -- ")
		header = _join_non_empty([
			f"\\textbf{{{org}}}" if org else "",
			f"\\hfill {date_range}" if date_range else "",
		], sep=" ")
		title = _escape_latex(leader.title)
		bullets = _format_itemize(leader.bullets)
		parts = []
		if header:
			parts.append(header + " \\")
		if title:
			parts.append(title)
		if bullets:
			parts.append(bullets)
		if parts:
			entries.append("\n".join(parts))
	return _section("Leadership Experience", "\n\n".join(entries))


def _render_awards(resume: Resume) -> str:
	awards = [award for award in resume.awards if award.strip()]
	return _section("Awards", _format_itemize(awards))


def render_resume_to_latex(resume: Resume, template_tex: str) -> str:
	replacements = {
		"HEADER_BLOCK": _render_header(resume),
		"EDUCATION_BLOCK": _render_education(resume),
		"EXPERIENCE_BLOCK": _render_experience(resume),
		"PROJECTS_BLOCK": _render_projects(resume),
		"SKILLS_BLOCK": _render_skills(resume),
		"LEADERSHIP_BLOCK": _render_leadership(resume),
		"AWARDS_BLOCK": _render_awards(resume),
	}

	rendered = template_tex
	for key, value in replacements.items():
		rendered = rendered.replace(f"{{{{{key}}}}}", value.strip())

	return rendered
