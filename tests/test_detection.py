from copilot.detection import heuristics
from tests.conftest import make_ocr


def test_detects_question_mark_question():
    ocr = make_ocr([
        "Vaga: Desenvolvedor Backend Pleno",
        "Por que voce quer trabalhar na Empresa X?",
        "Enviar candidatura",
    ])
    analysis = heuristics.analyze(ocr)
    assert len(analysis.questions) == 1
    assert analysis.questions[0].text == "Por que voce quer trabalhar na Empresa X?"
    assert analysis.questions[0].kind == "motivation"


def test_detects_imperative_question_without_mark():
    ocr = make_ocr([
        "Descreva uma situacao em que voce recebeu um feedback dificil",
    ])
    analysis = heuristics.analyze(ocr)
    assert len(analysis.questions) == 1
    assert analysis.questions[0].kind == "behavioral"


def test_detects_char_limit_nearby():
    ocr = make_ocr([
        "Conte sobre sua experiencia com Python",
        "Maximo de 500 caracteres",
    ])
    analysis = heuristics.analyze(ocr)
    assert analysis.questions[0].char_limit == 500


def test_detects_char_limit_counter_format():
    ocr = make_ocr(["Explique por que essa vaga te interessa", "0/300"])
    analysis = heuristics.analyze(ocr)
    assert analysis.questions[0].char_limit == 300


def test_multiple_choice_options():
    ocr = make_ocr([
        "Qual seu nivel de ingles?",
        "( ) Basico",
        "( ) Intermediario",
        "( ) Avancado",
    ])
    analysis = heuristics.analyze(ocr)
    question = analysis.questions[0]
    assert question.kind == "multiple_choice"
    assert question.options == ["Basico", "Intermediario", "Avancado"]


def test_salary_kind():
    ocr = make_ocr(["Qual a sua pretensao salarial?"])
    analysis = heuristics.analyze(ocr)
    assert analysis.questions[0].kind == "salary"


def test_ignores_short_ui_noise():
    ocr = make_ocr(["Salvar", "Cancelar", "Menu", "Perfil", "Sair?"])
    analysis = heuristics.analyze(ocr)
    assert analysis.questions == []


def test_job_signals_collected():
    ocr = make_ocr([
        "Requisitos: Python, Django, 3 anos de experiencia",
        "Nossos valores: transparencia e autonomia",
    ])
    analysis = heuristics.analyze(ocr)
    assert analysis.job_signals.requirement_snippets
    assert analysis.job_signals.culture_snippets


def test_platform_hint():
    ocr = make_ocr(["Bem-vindo ao Gupy", "Descreva sua experiencia com backend"])
    analysis = heuristics.analyze(ocr)
    assert analysis.platform_hint == "gupy"


def test_ambiguity_flag():
    empty = heuristics.analyze(make_ocr(["Texto longo sem pergunta " * 20]))
    assert heuristics.is_ambiguous(empty, make_ocr(["Texto longo sem pergunta " * 20]))
