import unittest
from unittest.mock import Mock

from cleanup import BUCKET, OWNER, delete_batch, empty_bucket


class CleanupTests(unittest.TestCase):
    def test_retries_only_transiently_failed_keys(self):
        client = Mock()
        client.delete_objects.side_effect = [
            {"Errors": [{"Key": "b", "Code": "SlowDown"}]}, {},
        ]
        self.assertEqual(delete_batch(client, ["a", "b"], sleep=lambda _: None), 2)
        self.assertEqual(client.delete_objects.call_args_list[1].kwargs["Delete"]["Objects"], [{"Key": "b"}])
        for call in client.delete_objects.call_args_list:
            self.assertEqual(call.kwargs["Bucket"], BUCKET)
            self.assertEqual(call.kwargs["ExpectedBucketOwner"], OWNER)

    def test_access_denial_fails_instead_of_claiming_success(self):
        client = Mock()
        client.delete_objects.return_value = {"Errors": [{"Key": "a", "Code": "AccessDenied"}]}
        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            delete_batch(client, ["a"], sleep=lambda _: None)
        self.assertEqual(client.delete_objects.call_count, 1)

    def test_transient_errors_have_bounded_retries(self):
        client = Mock()
        client.delete_objects.return_value = {"Errors": [{"Key": "a", "Code": "InternalError"}]}
        with self.assertRaisesRegex(RuntimeError, "after retries"):
            delete_batch(client, ["a"], sleep=lambda _: None)
        self.assertEqual(client.delete_objects.call_count, 5)

    def test_pagination_batches_and_final_verification(self):
        client = Mock()
        # Oversized fake page also checks the API's 1,000-key request limit.
        client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": str(i)} for i in range(1501)]}, {},
        ]
        client.delete_objects.return_value = {}
        client.list_objects_v2.return_value = {}
        self.assertEqual(empty_bucket(client, report=Mock(), workers=2), 1501)
        sizes = sorted(len(call.kwargs["Delete"]["Objects"]) for call in client.delete_objects.call_args_list)
        self.assertEqual(sizes, [501, 1000])
        client.list_objects_v2.assert_called_once_with(Bucket=BUCKET, ExpectedBucketOwner=OWNER, MaxKeys=1)

    def test_remaining_objects_trigger_another_scan(self):
        client = Mock()
        client.get_paginator.return_value.paginate.side_effect = [
            [{"Contents": [{"Key": "a"}]}], [{"Contents": [{"Key": "b"}]}],
        ]
        client.delete_objects.return_value = {}
        client.list_objects_v2.side_effect = [{"Contents": [{"Key": "b"}]}, {}]
        self.assertEqual(empty_bucket(client, report=Mock(), workers=1), 2)

    def test_never_reports_success_while_objects_remain(self):
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [{}]
        client.list_objects_v2.return_value = {"Contents": [{"Key": "remaining"}]}
        with self.assertRaisesRegex(RuntimeError, "still nonempty"):
            empty_bucket(client, report=Mock(), workers=1)


if __name__ == "__main__":
    unittest.main()
