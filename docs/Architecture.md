\# TapeLadySuite8 Architecture



Client

&#x20;   └── Job

&#x20;           └── Batch

&#x20;                   └── Receipt



Each processing run creates a new Batch.



Review operates on a selected Batch.



Exports operate on a selected Batch.



Historical batches remain available.

