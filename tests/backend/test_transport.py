import asyncio, json, shlex, time
from nova_backend.driver import WrightDriver


class LocalTransport(WrightDriver):
    """Run only the bridge's generated Python locally, with no SSH or GPU calls."""

    async def ssh(self, script, data=None, timeout=20):
        process = await asyncio.create_subprocess_exec(
            *shlex.split(script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(process.communicate(data), timeout)
        assert process.returncode == 0, err.decode()
        return out.decode()


async def test_inbox_result_partial_write_and_stable_cancel(tmp_path):
    (tmp_path / "inbox.jsonl").write_text("")
    (tmp_path / "cancel").write_text("")
    driver = LocalTransport(tmp_path)
    driver.session = {"root": str(tmp_path), "job_id": "MOCK"}
    before = (tmp_path / "cancel").stat().st_ino

    async def worker():
        while not (tmp_path / "inbox.jsonl").read_text():
            await asyncio.sleep(0.01)
        lines = (tmp_path / "inbox.jsonl").read_text().splitlines()
        assert len(lines) == 1
        b = json.loads(lines[0])
        out = tmp_path / ("result-" + b["id"] + ".json")
        out.write_text("{")
        await asyncio.sleep(0.1)
        out.write_text(json.dumps({"ok": True, "result": {"observed": True}}))

    task = asyncio.create_task(worker())
    assert await driver.rpc("inspect", deadline=time.time() + 5) == {"observed": True}
    await task
    await driver.cancel()
    assert (tmp_path / "cancel").read_text() == "cancel"
    assert (tmp_path / "cancel").stat().st_ino == before
