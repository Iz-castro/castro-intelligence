# Use text search

> [!WARNING]
>
> **Preview**
>
>
> This product or feature is
>
> subject to the "Pre-GA Offerings Terms" in the General Service Terms section
> of the [Service Specific
> Terms](https://docs.cloud.google.com/terms/service-terms#1).
>
> Pre-GA products and features are available "as is" and might have limited support.
>
> For more information, see the
> [launch stage descriptions](https://cloud.google.com/products/#product-launch-stages).

Use text search features in Firestore to search for specific strings
within documents.

## Edition requirements

Text search requires a Firestore Enterprise edition database.

## Before you begin

To perform a text search, you must first
[create text indexes](https://docs.cloud.google.com/firestore/native/docs/enterprise-indexing#create-text-index) for the fields you need to
search through.

## Run a text search

To perform a text search, use the `documentMatches` expression within the
`query` parameter of the `search(...)` stage.

The operation searches only in the fields indexed with a text index.
If multiple indexes are available, Firestore selects one
index to use for the operation.

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles')
  }));
```

##### iOS

```swift
let snapshot = try await db.pipeline().collection("restaurants")
  .search(query: DocumentMatches("waffles"))
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage.withQuery(documentMatches("waffles")))
```

##### Java
Android

```java
Pipeline pipeline = db.pipeline().collection("restaurants")
        .search(SearchStage.withQuery(documentMatches("waffles")));
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles')
  })
  .execute();
```

##### Python

```python
from google.cloud.firestore_v1.pipeline_expressions import DocumentMatches

results = (
    client.pipeline()
    .collection("restaurants")
    .search(DocumentMatches("waffles"))
    .execute()
)
```

##### Java

```java
Pipeline.Snapshot results1 =
    firestore.pipeline().collection("restaurants")
        .search(Search.withQuery(documentMatches("waffles")))
        .execute().get();
```

##### Go

```go
snapshot := client.Pipeline().
	Collection("restaurants").
	Search(firestore.WithSearchQuery(firestore.DocumentMatches("waffles"))).
	Execute(ctx)
```

### Search for an exact term

To search for an exact term, enclose the term in quotes (`"`):

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('"belgian waffles"')
  }));
```

##### iOS

```swift
let snapshot = try await db.pipeline().collection("restaurants")
  .search(query: DocumentMatches("\"belgian waffles\""))
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage.withQuery(documentMatches("\"belgian waffles\"")))
```

##### Java
Android

```java
Pipeline pipeline = db.pipeline().collection("restaurants")
        .search(SearchStage.withQuery(documentMatches("\"belgian waffles\"")));
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('"belgian waffles"')
  })
  .execute();
```

##### Python

```python
from google.cloud.firestore_v1.pipeline_expressions import DocumentMatches

results = (
    client.pipeline()
    .collection("restaurants")
    .search(DocumentMatches('"belgian waffles"'))
    .execute()
)
```

##### Java

```java
Pipeline.Snapshot results2 =
    firestore.pipeline().collection("restaurants")
        .search(Search.withQuery(documentMatches("\"belgian waffles\"")))
        .execute().get();
```

##### Go

```go
snapshot := client.Pipeline().
	Collection("restaurants").
	Search(firestore.WithSearchQuery(firestore.DocumentMatches("\"belgian waffles\""))).
	Execute(ctx)
```

### Search for a term combination

To search for combination for terms (logical `AND`), separate the terms
with spaces:

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles eggs')
  }));
```

##### iOS

```swift
let snapshot = try await db.pipeline().collection("restaurants")
  .search(query: DocumentMatches("waffles eggs"))
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage.withQuery(documentMatches("waffles eggs")))
```

##### Java
Android

```java
Pipeline pipeline = db.pipeline().collection("restaurants")
        .search(SearchStage.withQuery(documentMatches("waffles eggs")));
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles eggs')
  })
  .execute();
```

##### Python

```python
from google.cloud.firestore_v1.pipeline_expressions import DocumentMatches

results = (
    client.pipeline()
    .collection("restaurants")
    .search(DocumentMatches("waffles eggs"))
    .execute()
)
```

##### Java

```java
firestore.collection("restaurants").add(new HashMap<String, Object>() {{
  put("name", "Morning Diner");
  put("description", "Start your day with waffles and eggs.");
}});
Pipeline.Snapshot results3 =
    firestore.pipeline().collection("restaurants")
        .search(Search.withQuery(documentMatches("waffles eggs")))
        .execute().get();
```

##### Go

```go
snapshot := client.Pipeline().
	Collection("restaurants").
	Search(firestore.WithSearchQuery(firestore.DocumentMatches("waffles eggs"))).
	Execute(ctx)
```

### Exclude a term

To exclude a term, prefix the term with a hyphen (`-`):

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('coffee -waffles')
  }));
```

##### iOS

```swift
let snapshot = try await db.pipeline().collection("restaurants")
  .search(query: DocumentMatches("coffee -waffles"))
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage.withQuery(documentMatches("waffles eggs")))
```

##### Java
Android

```java
Pipeline pipeline = db.pipeline().collection("restaurants")
        .search(SearchStage.withQuery(documentMatches("coffee -waffles")));
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('-waffles')
  })
  .execute();
```

##### Python

```python
from google.cloud.firestore_v1.pipeline_expressions import DocumentMatches

results = (
    client.pipeline()
    .collection("restaurants")
    .search(DocumentMatches("-waffles"))
    .execute()
)
```

##### Java

```java
firestore.collection("restaurants").add(new HashMap<String, Object>() {{
  put("name", "City Coffee");
  put("description", "Premium coffee and pastries.");
}});
Pipeline.Snapshot results4 =
    firestore.pipeline().collection("restaurants")
        .search(Search.withQuery(documentMatches("-waffles")))
        .execute().get();
```

##### Go

```go
snapshot := client.Pipeline().
	Collection("restaurants").
	Search(firestore.WithSearchQuery(firestore.DocumentMatches("-waffles"))).
	Execute(ctx)
```

You can also exclude a phrase, for example, `pizza -"New York"`.

### Sort results

By default, Firestore
**sorts results by document creation time**, newest to oldest. You can sort
by search score instead, but this requires more computation to calculate
and compare the exact score of each document:

To sort results by search score:

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles'),
    sort: score().descending()
  }));
```

##### iOS

```
let snapshot = try await db.pipeline().collection("restaurants")
  .search(
      query: DocumentMatches("waffles"),
      sort: [Score().descending()]
      )
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage
              .withQuery(documentMatches("waffles"))
              .withSort(score().descending())
              )
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: documentMatches('waffles'),
    sort: score().descending()
  })
  .execute();
```

### Add fields to documents returned by the search stage

You can use `addFields` to add fields to the documents returned by the
search stage. Expressions returning values computed by the search stage,
like `score()`, can be used within `addFields` in the search stage to write
those \`values to the output documents.

The following example adds the score field to the documents returned by the
search stage:

### Web version 9

```javascript
const result = await execute(db.pipeline().collection('restaurants')
  .search({
    query: 'menu:waffles',
    addFields: [
        score().as('score'),
    ]
  }));
```

##### iOS

```swift
let snapshot = try await db.pipeline().collection("restaurants")
  .search(
    query: DocumentMatches("waffles"),
    addFields: [
      Score().as("score")
    ]
  )
  .execute()
```

##### Kotlin
Android

```kotlin
val pipeline = db.pipeline().collection("restaurants")
    .search(SearchStage.withQuery(documentMatches("waffles eggs")))
```

##### Java
Android

```java
Pipeline pipeline = db.pipeline().collection("restaurants")
        .search(
                SearchStage.withQuery(documentMatches("menu:waffles"))
                        .withAddFields(score().alias("score")));
```

##### Node.js

```javascript
await db.pipeline().collection('restaurants')
  .search({
    query: field('menu').matches('waffles'),
    addFields: [
        score().as('score'),
    ]
  }).execute();
```

##### Python

```python
from google.cloud.firestore_v1.pipeline_expressions import DocumentMatches, Score
from google.cloud.firestore_v1.pipeline_stages import SearchOptions

results = (
    client.pipeline()
    .collection("restaurants")
    .search(
        SearchOptions(
            query=DocumentMatches("menu:waffles"),
            add_fields=[Score().as_("score")],
        )
    )
    .execute()
)
```

##### Java

```java
Pipeline.Snapshot results5 =
    firestore.pipeline().collection("restaurants")
        .search(Search.withQuery(field("menu").regexMatch("waffles"))
            .withAddFields(score().as("score")))
        .execute().get();
```

##### Go

```go
snapshot := client.Pipeline().
	Collection("restaurants").
	Search(
		firestore.WithSearchQuery(firestore.FieldOf("menu").RegexMatch("waffles")),
		firestore.WithSearchAddFields(firestore.Score().As("score")),
	).
	Execute(ctx)
```