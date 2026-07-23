import queue
import threading

from stalker_gamma_linux.gui.worker import (
    BackgroundTask,
    DoneEvent,
    FailedEvent,
    QueueReporter,
    ReporterEvent,
    WorkerEvent,
)


def _drain(events: queue.Queue[WorkerEvent]) -> list[WorkerEvent]:
    drained: list[WorkerEvent] = []
    while True:
        try:
            drained.append(events.get_nowait())
        except queue.Empty:
            return drained


def test_queue_reporter_forwards_each_method_as_typed_event() -> None:
    events: queue.Queue[WorkerEvent] = queue.Queue()
    reporter = QueueReporter(events)

    reporter.header("Installation…")
    reporter.step("2/5", "Modpack GAMMA…")
    reporter.skip("1/5", "Anomaly (jeu de base)")
    reporter.progress("[+] téléchargement")
    reporter.success("Terminé")
    reporter.warn("Prérequis manquants")
    reporter.error("boom", hint="relance la commande")

    drained = _drain(events)
    assert drained == [
        ReporterEvent("header", "Installation…"),
        ReporterEvent("step", "Modpack GAMMA…", index="2/5"),
        ReporterEvent("skip", "Anomaly (jeu de base)", index="1/5"),
        ReporterEvent("progress", "[+] téléchargement"),
        ReporterEvent("success", "Terminé"),
        ReporterEvent("warn", "Prérequis manquants"),
        ReporterEvent("error", "boom", hint="relance la commande"),
    ]


def test_background_task_runs_func_and_reports_done() -> None:
    def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        events.put(ReporterEvent("progress", "travail…"))
        return 0

    task = BackgroundTask(job)
    task.start()
    task.join(timeout=2)

    drained = _drain(task.events)
    assert drained == [ReporterEvent("progress", "travail…"), DoneEvent(0)]


def test_background_task_cancel_sets_event_visible_to_job() -> None:
    observed: list[bool] = []

    def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        cancel_event.wait(timeout=2)
        observed.append(cancel_event.is_set())
        return 130

    task = BackgroundTask(job)
    task.start()
    task.cancel()
    task.join(timeout=2)

    assert observed == [True]
    drained = _drain(task.events)
    assert drained == [DoneEvent(130)]


def test_background_task_reports_unexpected_exception_as_failed_event() -> None:
    def job(events: queue.Queue[WorkerEvent], cancel_event: threading.Event) -> int:
        raise RuntimeError("bug inattendu")

    task = BackgroundTask(job)
    task.start()
    task.join(timeout=2)

    drained = _drain(task.events)
    assert len(drained) == 1
    assert isinstance(drained[0], FailedEvent)
    assert str(drained[0].error) == "bug inattendu"
