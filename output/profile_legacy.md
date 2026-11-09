# Legacy schema profile

## CUSTMAST — 419 rows

| column | null/blank % | distinct | top patterns |
|---|---|---|---|
| CUST_NO | 0.0 | 419 | `9999999`, ` 9999999` |
| CUST_NAME | 0.0 | 322 | `aaaaaa, aaaa`, `aaaaaa, aaaaa`, `aaaaaa,aaaa ` |
| PHONE | 11.5 | 318 | `(999) 999-9999`, `a/a`, `+9 999 999 9999` |
| EMAIL | 31.0 | 251 | ``, `aaaaa999@aaaa.aa`, `aaaa999@aaaa.aa` |
| STAT_CD | 0.0 | 4 | `a` |
| OPEN_DT | 0.0 | 409 | `9999-99-99`, `99999999`, `99/99/9999` |

## PREMISE — 400 rows

| column | null/blank % | distinct | top patterns |
|---|---|---|---|
| PREM_ID | 0.0 | 400 | `a999999` |
| CUST_NO | 0.0 | 400 | `9999999` |
| ADDR1 | 0.0 | 398 | `9999 aaaaa aa`, `9999 aaaaaaaaa aa`, `9999 aaaaaa aa` |
| CITY | 0.0 | 4 | `aaaaaa` |
| POSTAL | 0.0 | 400 | `a9a 9a9`, `a9a9a9` |

## METER — 604 rows

| column | null/blank % | distinct | top patterns |
|---|---|---|---|
| METER_NO | 0.0 | 604 | `a999999` |
| PREM_ID | 0.0 | 400 | `a999999` |
| SVC_TYPE | 0.0 | 6 | `a` |
| INSTALL_DT | 0.0 | 596 | `99/99/9999`, `9999-99-99`, `99-aaa-9999` |

## READING — 3636 rows

| column | null/blank % | distinct | top patterns |
|---|---|---|---|
| METER_NO | 0.0 | 616 | `a999999` |
| READ_DT | 0.0 | 24 | `9999-99-99`, `99/99/9999`, `99999999` |
| READ_VAL | 0.0 | 2697 | `9999`, `999` |

## ARBAL — 400 rows

| column | null/blank % | distinct | top patterns |
|---|---|---|---|
| CUST_NO | 0.0 | 400 | `9999999` |
| BAL_AMT | 0.0 | 349 | `999.99`, `$999.99`, `99.99` |
