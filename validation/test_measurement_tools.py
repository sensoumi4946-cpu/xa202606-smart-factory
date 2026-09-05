@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:case_unknown_register_type a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresTemperature ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_903" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:hasUnit "celsius" ;
    sf:registerAddress 40001 ;
    sf:registerBase 40001 ;
    sf:functionCode 3 ;
    sf:registerType "int8" ;
    sf:scaleFactor "0.01"^^xsd:double ;
    sf:pollIntervalMs 2000 .

sf:case_scale_factor_as_string a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresHumidity ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_903" ;
    sf:belongsToSubsystem sf:TempHumiditySubsystem ;
    sf:hasUnit "percent" ;
    sf:registerAddress 40002 ;
    sf:registerBase 40001 ;
    sf:functionCode 3 ;
    sf:registerType "uint16" ;
    sf:scaleFactor "0.01" ;
    sf:pollIntervalMs 2000 .

sf:case_poll_interval_as_string a sf:ProtocolBinding ;
    sf:bindsProperty sf:measuresCount ;
    sf:transportProtocol "modbus" ;
    sf:deviceId "ESP32_904" ;
    sf:belongsToSubsystem sf:CountingSubsystem ;
    sf:hasUnit "count" ;
    sf:registerAddress 40010 ;
    sf:registerBase 40001 ;
    sf:functionCode 3 ;
    sf:registerType "uint16" ;
    sf:scaleFactor "1.0"^^xsd:double ;
    sf:pollIntervalMs "2000" .