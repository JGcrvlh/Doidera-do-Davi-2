"""Pontos de entrada.

    copilot                          -> aplicacao grafica (tray + overlay)
    copilot --set-api-key            -> guarda a chave no keyring do SO
    copilot --ask "pergunta"         -> gera resposta no console (sem captura)
    copilot --analyze-text arq.txt   -> roda o pipeline sobre texto (sem OCR)
    copilot --analyze-image tela.png -> roda o pipeline sobre uma imagem (OCR local)

Os modos de console existem para desenvolvimento e para validar o pipeline sem
ambiente grafico (fase A do MVP).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from pathlib import Path

from copilot.config import Settings


def _build_headless_orchestrator(settings: Settings, need_ocr: bool):
    from copilot.context.extractor import ContextExtractor
    from copilot.detection.llm_detector import LlmQuestionDetector
    from copilot.domain import events as ev
    from copilot.domain.profile import load_profile
    from copilot.generation.generator import AnswerGenerator
    from copilot.generation.verifier import AnswerVerifier
    from copilot.llm.client import LlmClient
    from copilot.orchestrator.pipeline import Orchestrator
    from copilot.research.researcher import CompanyResearcher
    from copilot.storage.db import create_db
    from copilot.storage.repository import Repository

    settings.ensure_dirs()
    profile = load_profile(settings.resolved_profile_path())
    _, session_factory = create_db(settings.db_path)
    repository = Repository(session_factory)
    llm = LlmClient(settings)

    bus = ev.EventBus()
    bus.subscribe(lambda event: print(f"  [{type(event).__name__}]", file=sys.stderr))

    class _NoCapture:
        def capture(self):
            raise RuntimeError("Captura de tela indisponivel no modo console")

        def in_scope(self, *_args):
            return True

    if need_ocr:
        from copilot.ocr.rapidocr import RapidOcrService

        ocr = RapidOcrService(settings)
    else:
        class _NoOcr:
            def run(self, capture):
                raise RuntimeError("OCR nao necessario neste modo")

        ocr = _NoOcr()

    orchestrator = Orchestrator(
        settings=settings,
        bus=bus,
        repository=repository,
        profile=profile,
        capture=_NoCapture(),
        ocr=ocr,
        llm_detector=LlmQuestionDetector(llm),
        extractor=ContextExtractor(llm),
        researcher=CompanyResearcher(llm, repository, settings.research_ttl_days),
        generator=AnswerGenerator(llm, AnswerVerifier(llm)),
        cost_tracker=llm.costs,
    )
    return orchestrator, llm


def _print_bundle(bundle) -> None:
    print("\n=== PERGUNTA DETECTADA ===")
    print(bundle.question.text)
    print("\n=== RESPOSTA SUGERIDA ===")
    print(bundle.suggestion.answer)
    if bundle.suggestion.rationale:
        print("\n--- Por que assim ---")
        print(bundle.suggestion.rationale)
    if bundle.suggestion.facts_used:
        print("\nFatos do perfil usados:", ", ".join(bundle.suggestion.facts_used))
    if bundle.suggestion.caveats:
        print("Ressalvas:", " | ".join(bundle.suggestion.caveats))
    problems = bundle.verification.issues + bundle.verification.unsupported_claims
    if problems:
        print("\n⚠ VERIFICACAO:", " | ".join(problems))
    print(f"\nCusto desta rodada: ~US$ {bundle.cost_usd:.3f}")


def _cmd_analyze_text(settings: Settings, text: str) -> int:
    orchestrator, _ = _build_headless_orchestrator(settings, need_ocr=False)
    bundle = asyncio.run(orchestrator.analyze(text_override=text))
    if bundle is None:
        print("Nenhuma pergunta detectada / pipeline interrompido.")
        return 1
    _print_bundle(bundle)
    return 0


def _cmd_analyze_image(settings: Settings, path: Path) -> int:
    from PIL import Image

    from copilot.domain.models import RawCapture

    image = Image.open(path)
    orchestrator, _ = _build_headless_orchestrator(settings, need_ocr=True)
    capture = RawCapture(
        png=path.read_bytes(), width=image.width, height=image.height,
        window_title=path.name,
    )
    orchestrator.allow_out_of_scope = True
    bundle = asyncio.run(orchestrator.analyze(capture=capture))
    if bundle is None:
        print("Nenhuma pergunta detectada / pipeline interrompido.")
        return 1
    _print_bundle(bundle)
    return 0


def _cmd_ask(settings: Settings, question_text: str) -> int:
    from copilot.domain.models import DetectedQuestion
    from copilot.domain.profile import load_profile
    from copilot.generation.generator import AnswerGenerator
    from copilot.generation.verifier import AnswerVerifier
    from copilot.llm.client import LlmClient

    settings.ensure_dirs()
    profile = load_profile(settings.resolved_profile_path())
    llm = LlmClient(settings)
    generator = AnswerGenerator(llm, AnswerVerifier(llm))
    suggestion, verification = generator.generate(
        question=DetectedQuestion(text=question_text),
        profile=profile,
        job_context=None,
        company=None,
    )
    print("\n=== RESPOSTA SUGERIDA ===")
    print(suggestion.answer)
    if suggestion.caveats:
        print("\nRessalvas:", " | ".join(suggestion.caveats))
    problems = verification.issues + verification.unsupported_claims
    if problems:
        print("\n⚠ VERIFICACAO:", " | ".join(problems))
    print(f"\nCusto: ~US$ {llm.costs.total_usd:.3f}")
    return 0


def _cmd_set_api_key() -> int:
    from copilot.llm.client import store_api_key

    key = getpass.getpass("Cole a chave da Claude API (sk-ant-...): ").strip()
    if not key:
        print("Nada salvo.")
        return 1
    store_api_key(key)
    print("Chave salva no keyring do sistema.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copilot", description=__doc__)
    parser.add_argument("--profile", type=Path, help="caminho do profile.yaml")
    parser.add_argument("--set-api-key", action="store_true")
    parser.add_argument("--ask", metavar="PERGUNTA")
    parser.add_argument("--analyze-text", metavar="ARQUIVO",
                        help="arquivo de texto simulando o OCR da tela (- para stdin)")
    parser.add_argument("--analyze-image", type=Path, metavar="IMAGEM")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = Settings()
    if args.profile:
        settings.profile_path = args.profile

    if args.set_api_key:
        return _cmd_set_api_key()
    if args.ask:
        return _cmd_ask(settings, args.ask)
    if args.analyze_text:
        text = (
            sys.stdin.read() if args.analyze_text == "-"
            else Path(args.analyze_text).read_text(encoding="utf-8")
        )
        return _cmd_analyze_text(settings, text)
    if args.analyze_image:
        return _cmd_analyze_image(settings, args.analyze_image)

    from copilot.ui.app import run_gui

    return run_gui(settings)


if __name__ == "__main__":
    raise SystemExit(main())
