# Natural OpenAPI Drift Results

- Version pairs: 60
- Total alerts: 5969
- Alert layers: {'non_breaking': 4029, 'semantic': 416, 'compatibility': 1524}

## Top Alert Types

| Alert type | Count |
|---|---:|
| schema_field_added | 3553 |
| schema_field_removed | 1112 |
| operation_added | 476 |
| deep_enum_signature_removed | 385 |
| operation_removed | 323 |
| field_requiredness_changed | 76 |
| enum_values_changed | 31 |
| field_type_or_format_changed | 13 |

## Pair-Level Summary

| Pair | Alerts | Compatibility | Semantic | Security | Non-breaking | Path |
|---|---:|---:|---:|---:|---:|---|
| pair_0001 | 21 | 1 | 2 | 0 | 18 | `adyen.com:AccountService` |
| pair_0002 | 123 | 31 | 2 | 0 | 90 | `adyen.com:AccountService` |
| pair_0003 | 64 | 6 | 12 | 0 | 46 | `adyen.com:AccountService` |
| pair_0004 | 403 | 210 | 44 | 0 | 149 | `adyen.com:BalancePlatformService` |
| pair_0005 | 3 | 0 | 0 | 0 | 3 | `adyen.com:BinLookupService` |
| pair_0006 | 2 | 0 | 0 | 0 | 2 | `adyen.com:BinLookupService` |
| pair_0007 | 2 | 1 | 0 | 0 | 1 | `adyen.com:BinLookupService` |
| pair_0008 | 84 | 2 | 0 | 0 | 82 | `adyen.com:CheckoutService` |
| pair_0009 | 9 | 0 | 0 | 0 | 9 | `adyen.com:CheckoutService` |
| pair_0010 | 1 | 0 | 0 | 0 | 1 | `adyen.com:CheckoutService` |
| pair_0011 | 32 | 13 | 0 | 0 | 19 | `adyen.com:FundService` |
| pair_0012 | 0 | 0 | 0 | 0 | 0 | `adyen.com:FundService` |
| pair_0013 | 5 | 3 | 2 | 0 | 0 | `adyen.com:HopService` |
| pair_0014 | 0 | 0 | 0 | 0 | 0 | `adyen.com:HopService` |
| pair_0015 | 61 | 6 | 13 | 0 | 42 | `adyen.com:LegalEntityService` |
| pair_0016 | 60 | 12 | 0 | 0 | 48 | `adyen.com:LegalEntityService` |
| pair_0017 | 33 | 4 | 2 | 0 | 27 | `adyen.com:MarketPayNotificationService` |
| pair_0018 | 109 | 24 | 2 | 0 | 83 | `adyen.com:MarketPayNotificationService` |
| pair_0019 | 62 | 8 | 4 | 0 | 50 | `adyen.com:MarketPayNotificationService` |
| pair_0020 | 0 | 0 | 0 | 0 | 0 | `adyen.com:NotificationConfigurationService` |
| pair_0021 | 0 | 0 | 0 | 0 | 0 | `adyen.com:NotificationConfigurationService` |
| pair_0022 | 0 | 0 | 0 | 0 | 0 | `adyen.com:NotificationConfigurationService` |
| pair_0023 | 24 | 0 | 0 | 0 | 24 | `adyen.com:PaymentService` |
| pair_0024 | 167 | 0 | 0 | 0 | 167 | `adyen.com:PaymentService` |
| pair_0025 | 8 | 0 | 0 | 0 | 8 | `adyen.com:PaymentService` |
| pair_0026 | 5 | 0 | 0 | 0 | 5 | `adyen.com:PayoutService` |
| pair_0027 | 364 | 38 | 4 | 0 | 322 | `adyen.com:PayoutService` |
| pair_0028 | 5 | 0 | 0 | 0 | 5 | `adyen.com:PayoutService` |
| pair_0029 | 55 | 19 | 1 | 0 | 35 | `adyen.com:RecurringService` |
| pair_0030 | 0 | 0 | 0 | 0 | 0 | `adyen.com:RecurringService` |
| pair_0031 | 19 | 0 | 0 | 0 | 19 | `adyen.com:RecurringService` |
| pair_0032 | 42 | 17 | 0 | 0 | 25 | `adyen.com:TransferService` |
| pair_0033 | 113 | 23 | 1 | 0 | 89 | `adyen.com:TransferService` |
| pair_0034 | 491 | 74 | 5 | 0 | 412 | `amazonaws.com:appmesh` |
| pair_0035 | 59 | 38 | 2 | 0 | 19 | `amazonaws.com:clouddirectory` |
| pair_0036 | 65 | 27 | 5 | 0 | 33 | `amazonaws.com:cloudfront` |
| pair_0037 | 192 | 31 | 4 | 0 | 157 | `amazonaws.com:cloudfront` |
| pair_0038 | 175 | 125 | 4 | 0 | 46 | `amazonaws.com:cloudfront` |
| pair_0039 | 314 | 87 | 50 | 0 | 177 | `amazonaws.com:cloudsearch` |
| pair_0040 | 723 | 35 | 14 | 0 | 674 | `amazonaws.com:dynamodb` |
| pair_0041 | 531 | 38 | 4 | 0 | 489 | `amazonaws.com:lambda` |
| pair_0042 | 96 | 2 | 50 | 0 | 44 | `amazonaws.com:rds` |
| pair_0043 | 92 | 0 | 50 | 0 | 42 | `amazonaws.com:rds` |
| pair_0044 | 85 | 1 | 50 | 0 | 34 | `amazonaws.com:rds` |
| pair_0045 | 185 | 38 | 12 | 0 | 135 | `apicurio.local:registry` |
| pair_0046 | 14 | 8 | 2 | 0 | 4 | `azure.com:advisor` |
| pair_0047 | 29 | 0 | 0 | 0 | 29 | `azure.com:advisor` |
| pair_0048 | 18 | 6 | 0 | 0 | 12 | `azure.com:advisor` |
| pair_0049 | 83 | 28 | 8 | 0 | 47 | `azure.com:alertsmanagement-AlertsManagement` |
| pair_0050 | 46 | 0 | 1 | 0 | 45 | `azure.com:alertsmanagement-AlertsManagement` |