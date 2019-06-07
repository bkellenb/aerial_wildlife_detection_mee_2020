/* 
    Template for database setup. Requires strings to be escaped:
    - &dbName
    - &schema
    - &owner
    - &user
    - &password
    - etc.

    TODO: just here for orientation; needs massive restructuring to actually work.
    Probably has tons of bugs as well; need to try out...

    2019 Benjamin Kellenberger
*/

/* extensions and trigger functions */
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


/* schema */
CREATE SCHEMA IF NOT EXISTS &schema
    AUTHORIZATION &user;


/* tables */
CREATE TABLE IF NOT EXISTS &schema.IMAGE (
    id uuid DEFAULT uuid_generate_v4(),
    filename VARCHAR NOT NULL,
    exif VARCHAR,
    fVec bytea,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS &schema.LABELCLASS (
    id uuid DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS &schema.ANNOTATION (
    id uuid DEFAULT uuid_generate_v4(),
    imageID uuid NOT NULL,
    timeCreated TIMESTAMP NOT NULL DEFAULT NOW(),
    timeRequired BIGINT,
    labelClass uuid NOT NULL,
    &annotationFields
    PRIMARY KEY (id),
    FOREIGN KEY (imageID) REFERENCES &schema.IMAGE(id),
    FOREIGN KEY (labelClass) REFERENCES &schema.LABELCLASS(id)
);

CREATE TABLE IF NOT EXISTS &schema.PREDICTION (
    id uuid DEFAULT uuid_generate_v4(),
    imageID uuid NOT NULL,
    timeCreated TIMESTAMP NOT NULL DEFAULT NOW(),
    &predictionFields
    priority real,
    PRIMARY KEY (id),
    FOREIGN KEY (imageID) REFERENCES &schema.IMAGE(id)
);

CREATE TABLE IF NOT EXISTS &schema.CNN (
    id uuid DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS &schema.CNN_LABELCLASS (
    cnnID uuid NOT NULL,
    labelclassID uuid NOT NULL,
    labelNumber BIGINT NOT NULL,
    PRIMARY KEY (cnnID, labelclassID),
    FOREIGN KEY (cnnID) REFERENCES &schema.CNN(id),
    FOREIGN KEY (labelclassID) REFERENCES &schema.LABELCLASS(id)
);

CREATE TABLE IF NOT EXISTS &schema.CNNSTATE (
    id uuid DEFAULT uuid_generate_v4(),
    cnnID uuid NOT NULL,
    timeCreated TIMESTAMP NOT NULL DEFAULT NOW(),
    stateDict bytea NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (cnnID) REFERENCES &schema.CNN(id)
);

/* TODO: integrate user account tables, reference from annotation table */
