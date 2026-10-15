import tempfile
import threading
import unittest

from adobe_stock_analytics.store import Store


class StoreThreadTest(unittest.TestCase):
    def test_parallel_use_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(d)
            errors = []

            def work(n):
                try:
                    for i in range(300):
                        st.set_state(f"k{n}", str(i))
                        st.db.execute("SELECT * FROM state WHERE key=?", (f"k{n}",)).fetchone()
                        st.db.execute("SELECT key FROM state").fetchall()
                except Exception as exc:  # noqa: BLE001
                    errors.append(repr(exc))

            ts = [threading.Thread(target=work, args=(n,)) for n in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(errors, [])
            self.assertEqual(st.get_state("k3"), "299")


if __name__ == "__main__":
    unittest.main()
