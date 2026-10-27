import pytest

from vnt.summarizer import (
    EndpointSummarizer,
    SummarizeError,
    SummaryChain,
    local_summary,
    parse_reply,
    truncate_to_word,
)


def test_parse_reply_clean_json():
    assert parse_reply('{"title": "Eggs", "summary": "Buy eggs."}') == ("Eggs", "Buy eggs.")


def test_parse_reply_fenced_json():
    text = '```json\n{"title": "Eggs", "summary": "Buy eggs."}\n```'
    assert parse_reply(text) == ("Eggs", "Buy eggs.")


def test_parse_reply_two_lines():
    text = "Title: Weird noise in car\nSummary: Memo about a strange engine sound."
    assert parse_reply(text) == ("Weird noise in car", "Memo about a strange engine sound.")


def test_parse_reply_garbage_returns_none():
    assert parse_reply("") is None


def test_parse_reply_json_with_extra_prose():
    text = 'Sure! {"title": "Eggs", "summary": "Buy eggs."} hope that helps'
    assert parse_reply(text) == ("Eggs", "Buy eggs.")


def test_local_summary_from_transcript():
    transcript = "please buy eggs and coffee. Also grab some bread."
    title, summary = local_summary(transcript, "memo.m4a")
    assert title == "Please buy eggs and coffee"
    assert summary.startswith("please buy eggs and coffee.")
    assert summary.endswith(".")


def test_local_summary_empty_transcript():
    title, summary = local_summary("", "voice-memo-2026.m4a")
    assert title == "Voice note voice memo 2026"
    assert summary == "(empty transcript)"


def test_truncate_to_word():
    assert truncate_to_word("hello world", 11) == "hello world"
    cut = truncate_to_word("hello world there", 11)
    assert cut.startswith("hello")
    assert cut.endswith("...")
    assert len(cut) <= 11
    assert len(truncate_to_word("a b c d e f g h i j k l m n o p", 12)) <= 12


def test_endpoint_summarizer_happy_path(server):
    summarizer = EndpointSummarizer(server.base_url)
    title, summary = summarizer.summarize("some transcript")
    assert title == "Fake Title"
    assert "Fake summary" in summary
    assert summarizer.name == "endpoint:fake-llm"


def test_endpoint_summarizer_respects_explicit_model(server):
    summarizer = EndpointSummarizer(server.base_url, model="my-model")
    summarizer.summarize("some transcript")
    assert summarizer.name == "endpoint:my-model"


def test_endpoint_summarizer_dead_endpoint():
    summarizer = EndpointSummarizer("http://127.0.0.1:9/v1", model="m")
    with pytest.raises(SummarizeError):
        summarizer.summarize("transcript")


def test_endpoint_summarizer_no_model_listed():
    from fake_server import FakeEndpointServer

    with FakeEndpointServer() as bare:
        bare.models = []
        summarizer = EndpointSummarizer(bare.base_url)
        with pytest.raises(SummarizeError, match="no models listed"):
            summarizer.summarize("transcript")


def test_chain_falls_back_to_local(server, capsys):
    unreachable = EndpointSummarizer("http://127.0.0.1:9/v1", model="m")
    chain = SummaryChain(unreachable)
    title, summary, tag = chain.summarize("buy eggs tomorrow please.", "memo.m4a")
    assert tag == "local-fallback"
    assert chain.used == "local-fallback"
    assert "endpoint summary failed" in capsys.readouterr().err


def test_chain_uses_endpoint_when_available(server):
    chain = SummaryChain(EndpointSummarizer(server.base_url))
    title, summary, tag = chain.summarize("transcript", "memo.m4a")
    assert (title, summary) == ("Fake Title", "Fake summary sentence.")
    assert tag.startswith("endpoint:")


def test_chain_without_endpoint_goes_local():
    chain = SummaryChain(None)
    title, summary, tag = chain.summarize("remind me", "memo.m4a")
    assert tag == "local-fallback"
