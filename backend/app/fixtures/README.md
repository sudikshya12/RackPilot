# Redfish fixtures

Hand-written JSON in the *shape* of DMTF Redfish resources (see the DMTF "Redfish Mockup" bundles,
DSP2043). File names encode the resource path: `/redfish/v1/Systems/1/Memory/A1` →
`redfish__v1__Systems__1__Memory__A1.json`.

How these differ from real hardware:
* Real BMCs populate different property subsets; e.g. `ProcessorSummary.Model` or `Oem` sections vary by vendor.
* `Oem.RackOpsRole` is a lab-specific tag used to mark the data interface; real systems have no such property.
* Real `LinkStatus` and `SpeedMbps` reflect live PHY state; here they are static.
* Real endpoints require authentication and TLS; fixtures have neither.
