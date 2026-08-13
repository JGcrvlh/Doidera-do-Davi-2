from copilot.privacy.redactor import redact


def test_redacts_email():
    report = redact("Contato: ana.dev@gmail.com para duvidas")
    assert "ana.dev@gmail.com" not in report.text
    assert "[EMAIL]" in report.text
    assert report.counts["EMAIL"] == 1


def test_redacts_cpf_and_phone():
    report = redact("CPF 123.456.789-01, tel (11) 91234-5678")
    assert "123.456.789-01" not in report.text
    assert "91234-5678" not in report.text
    assert report.counts["CPF"] == 1
    assert report.counts["TELEFONE"] == 1


def test_redacts_cnpj_and_cep():
    report = redact("CNPJ 12.345.678/0001-90, CEP 01310-100")
    assert "[CNPJ]" in report.text
    assert "[CEP]" in report.text


def test_keeps_job_content_intact():
    text = "Por que voce quer trabalhar na Empresa X? Requisitos: Python, 3 anos"
    report = redact(text)
    assert report.text == text
    assert report.total == 0


def test_redacts_credit_card():
    report = redact("cartao 4111 1111 1111 1111 final")
    assert "4111" not in report.text
    assert "[CARTAO]" in report.text
