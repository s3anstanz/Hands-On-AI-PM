import json

import pytest

import consume

WHERE = "Chapter 3 (Temperature: how the model picks), step 6 of 21, seed 41957"
OWNER = "s3anstanz"


def said(body, by=OWNER):
    return {"author": {"login": by}, "body": body}


def agent(body):
    return said(f"{consume.MARKER}\n{body}")


def issue(n, where=WHERE, labels=(), comments=()):
    """An open feedback issue as `gh issue list --json number,body,labels,comments` returns it."""
    body = f"### Your feedback\n\nx\n\n### Where in the tutorial\n\n{where}\n\n### Your setup\n\nmacOS, Chapter 9 (Cheat sheet) open"
    return {"number": n, "body": body, "labels": [{"name": name} for name in labels], "comments": list(comments)}


def test_chapter_from_the_where_field():
    assert consume.chapter_of(issue(1)["body"]) == "3"
    assert consume.chapter_of(issue(1, where="End of Chapter 8 (Design an AI feature), seed 5")["body"]) == "8"


def test_no_chapter_when_where_is_empty_or_free_text():
    for where in ("_No response_", "somewhere near the end", "", "\n"):
        assert consume.chapter_of(issue(1, where=where)["body"]) is None
    assert consume.chapter_of("no form at all, mentions Chapter 2 (Tokens) in passing") is None
    assert consume.chapter_of("### Where in the tutorial\n\n### Your setup\n\nChapter 9 (Cheat sheet)") is None


def test_closes_reads_every_keyword_and_number():
    assert consume.closes("Closes #43, closes #44\n\nFixes #4. Resolved #7") == {43, 44, 4, 7}
    assert consume.closes("see #43, not closing it") == set()


def q(issues, prs):
    return consume.queue(issues, prs, OWNER)


def test_new_issue_is_queued_with_its_chapter():
    assert q([issue(43)], []) == [consume.QueueItem(43, "3", "new")]


def test_needs_sean_is_skipped():
    assert q([issue(43, labels=("needs-sean",))], []) == []
    assert q([issue(43, labels=("cori", "needs-sean"))], []) == []


def test_routed_issue_waiting_for_a_build_is_pending_in_its_lane():
    # deferred past the cap, or handed off: it must come back every run until built
    for lane in ("cori", "frank"):
        comments = (agent(f"Handed off to {lane}: the code is fine"),)
        assert q([issue(43, labels=(lane,), comments=comments)], []) == [
            consume.QueueItem(43, "3", "pending", lane=lane)
        ]


def test_issue_with_an_open_pr_is_skipped():
    prs = [{"number": 50, "body": "Closes #43", "state": "OPEN"}]
    assert q([issue(43, labels=("in-progress",))], prs) == []
    assert q([issue(43, labels=("cori",))], prs) == []


def test_in_progress_without_an_open_pr_is_stale():
    assert q([issue(43, labels=("in-progress",))], []) == [consume.QueueItem(43, "3", "stale")]


def test_pr_closed_unmerged_names_the_latest_closed_pr():
    prs = [
        {"number": 50, "body": "Closes #43", "state": "CLOSED"},
        {"number": 61, "body": "Closes #43", "state": "CLOSED"},
    ]
    assert q([issue(43, labels=("cori",))], prs) == [consume.QueueItem(43, "3", "rejected", lane="cori", pr=61)]
    assert q([issue(43, labels=("cori", "needs-sean"))], prs) == []


def test_rejection_already_handled_is_not_rejected_again():
    prs = [{"number": 61, "body": "Closes #43", "state": "CLOSED"}]
    comments = (agent("Reworking after PR #61, with Sean's comments"),)
    assert q([issue(43, labels=("cori",), comments=comments)], prs) == [
        consume.QueueItem(43, "3", "pending", lane="cori")
    ]


def test_merged_pr_does_not_count_as_rejected():
    prs = [{"number": 50, "body": "Closes #43", "state": "MERGED"}]
    assert q([issue(43, labels=("cori",))], prs) == [consume.QueueItem(43, "3", "pending", lane="cori")]


def test_owner_replying_after_the_agent_requeues_it_with_the_reply():
    comments = (agent("Sent to Cori"), said("first"), said("Actually it's the 40-column view"))
    assert q([issue(43, labels=("cori",), comments=comments)], []) == [
        consume.QueueItem(43, "3", "requeued", lane="cori", notes=("first", "Actually it's the 40-column view"))
    ]


def test_someone_elses_reply_does_not_requeue():
    comments = (agent("Sent to Cori"), said("thanks!", by="a-tester"))
    assert q([issue(43, labels=("cori",), comments=comments)], []) == [
        consume.QueueItem(43, "3", "pending", lane="cori")
    ]


def test_reply_before_any_agent_comment_is_just_part_of_a_new_issue():
    assert q([issue(43, comments=(said("more detail"),))], []) == [consume.QueueItem(43, "3", "new")]


def test_reply_on_an_issue_with_an_open_pr_belongs_to_the_pr():
    comments = (agent("Sent to Cori"), said("looks good"))
    prs = [{"number": 50, "body": "Closes #43", "state": "OPEN"}]
    assert q([issue(43, labels=("cori",), comments=comments)], prs) == []


def test_queue_is_in_issue_number_order():
    assert [q.number for q in q([issue(48), issue(43)], [])] == [43, 48]


def r(n, lane, chapter):
    return {"number": n, "lane": lane, "chapter": chapter}


def test_same_lane_and_chapter_share_a_pr():
    build, deferred = consume.batches([r(43, "cori", "3"), r(44, "cori", "3"), r(47, "frank", "3")])
    assert build == [consume.Batch("cori", "3", (43, 44)), consume.Batch("frank", "3", (47,))]
    assert deferred == []


def test_no_chapter_gets_its_own_pr():
    build, _ = consume.batches([r(48, "cori", None), r(49, "cori", None)])
    assert build == [consume.Batch("cori", None, (48,)), consume.Batch("cori", None, (49,))]


def test_cap_counts_prs_and_defers_the_rest():
    routed = [r(n, "cori", str(n)) for n in (1, 2, 3, 4)] + [r(5, "cori", "1")]
    build, deferred = consume.batches(routed)
    assert [b.issues for b in build] == [(1, 5), (2,), (3,)]
    assert deferred == [4]


def test_unknown_lane_is_rejected():
    with pytest.raises(ValueError, match="lane"):
        consume.batches([r(1, "sean", "1")])


def test_cli_queue_prints_what_needs_a_decision(tmp_path, capsys):
    issues, prs = tmp_path / "issues.json", tmp_path / "prs.json"
    issues.write_text(json.dumps([issue(48, where="_No response_"), issue(43)]))
    prs.write_text("[]")
    assert consume.main(["queue", str(issues), str(prs), "--owner", OWNER]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"number": 43, "chapter": "3", "why": "new", "lane": None, "pr": None, "notes": []},
        {"number": 48, "chapter": None, "why": "new", "lane": None, "pr": None, "notes": []},
    ]


def test_cli_batches_prints_build_and_deferred(tmp_path, capsys):
    routed = tmp_path / "routed.json"
    routed.write_text(json.dumps([r(43, "cori", "3"), r(44, "cori", "3"), r(47, "frank", "3")]))
    assert consume.main(["batches", str(routed), "--cap", "1"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "build": [{"lane": "cori", "chapter": "3", "issues": [43, 44]}],
        "deferred": [47],
    }


def test_cli_bad_input_is_one_line(tmp_path, capsys):
    bad = tmp_path / "issues.json"
    entry = issue(1)
    broken = (
        {**entry, "number": "x"},
        {"number": 1},
        {**entry, "labels": ["cori"]},
        {**entry, "comments": [{"body": None}]},
    )
    for content in ("{not json", "{}", *(json.dumps([b]) for b in broken)):
        bad.write_text(content)
        assert consume.main(["queue", str(bad), str(bad), "--owner", OWNER]) == 2
        err = capsys.readouterr().err
        assert err.count("\n") == 1
        assert err.startswith(f"consume.py: {bad}:")
    bad.write_text(json.dumps([r(1, "sean", "1")]))
    assert consume.main(["batches", str(bad)]) == 2
    assert capsys.readouterr().err.startswith(f"consume.py: {bad}:")
    assert consume.main(["batches", str(tmp_path / "missing.json")]) == 2
    assert capsys.readouterr().err.startswith("consume.py: ")


# Trust: the repo is public, so anyone can open an issue that the Feedback form labels `feedback`.
# Only the owner's and listed testers' issues and comments may reach an agent.


def by(login, n, comments=()):
    return {**issue(n, comments=comments), "author": {"login": login}}


def screened(raw, logins=()):
    return consume.screen(raw, OWNER, frozenset(logins))


def test_strangers_issue_never_reaches_the_queue_and_is_listed_for_sean():
    safe, skipped = screened([by("stranger", 50), by(OWNER, 51)])
    assert [i["number"] for i in safe] == [51]
    assert skipped == [{"number": 50, "author": "stranger"}]


def test_listed_testers_issue_is_kept_and_logins_ignore_case():
    safe, skipped = screened([by("Tester-1", 52)], logins=("tester-1",))
    assert [i["number"] for i in safe] == [52] and skipped == []


def test_strangers_comments_are_dropped_from_trusted_issues():
    comments = [
        said("planted instructions", by="stranger"),
        agent("Routed to Cori"),
        said("use the sky example"),
        said("more context", by="tester-1"),
    ]
    (kept,), _ = screened([by(OWNER, 53, comments)], logins=("tester-1",))
    assert [c["body"] for c in kept["comments"]] == [comments[1]["body"], "use the sky example", "more context"]


def test_screened_output_is_what_queue_reads():
    safe, _ = screened([by(OWNER, 54)])
    assert q(safe, []) == [consume.QueueItem(54, "3", "new")]


def test_tester_list_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "trusted.txt"
    path.write_text("# testers\n\nTester-1\n  tester-2  \n")
    assert consume.load_testers(str(path)) == frozenset({"tester-1", "tester-2"})


def test_tester_list_rejects_a_line_that_is_not_a_login(tmp_path):
    path = tmp_path / "trusted.txt"
    path.write_text("tester-1\nnot a login!\n")
    with pytest.raises(ValueError, match="line 2"):
        consume.load_testers(str(path))


def test_cli_screen_prints_safe_issues_and_skipped(tmp_path, capsys):
    raw, listed = tmp_path / "raw.json", tmp_path / "trusted.txt"
    raw.write_text(json.dumps([by("stranger", 50), by("tester-1", 52, [said("hi", by="stranger")])]))
    listed.write_text("tester-1\n")
    assert consume.main(["screen", str(raw), "--owner", OWNER, "--testers", str(listed)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [i["number"] for i in out["issues"]] == [52] and out["issues"][0]["comments"] == []
    assert out["skipped"] == [{"number": 50, "author": "stranger"}]


def test_cli_screen_needs_each_issues_author(tmp_path, capsys):
    raw, listed = tmp_path / "raw.json", tmp_path / "trusted.txt"
    raw.write_text(json.dumps([issue(1)]))
    listed.write_text("")
    assert consume.main(["screen", str(raw), "--owner", OWNER, "--testers", str(listed)]) == 2
    assert capsys.readouterr().err.count("\n") == 1


def test_the_shipped_tester_list_loads():
    consume.load_testers(consume.TESTERS_PATH)
