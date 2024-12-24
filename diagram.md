flowchart TB
    subgraph " "
        IpsHandlerPolicy["IpsHandlerServiceRoleDefaultPolicy<br/>IAM::Policy"]-->IpsHandlerRole["IpsHandlerServiceRole<br/>IAM::Role"]
        IpsHandler[["IpsHandler<br/>Lambda::Function"]]-->IpsHandlerRole
        IpsHandlerLogRetention["IpsHandlerLogRetention<br/>Custom::LogRetention"]-->IpsHandler
        IpsHandlerLogRetention-->LogRetentionLambda[["LogRetention<br/>Lambda::Function"]]
        LogRetentionPolicy["LogRetentionServiceRoleDefaultPolicy<br/>IAM::Policy"]-->LogRetentionRole["LogRetentionServiceRole<br/>IAM::Role"]
        LogRetentionLambda-->LogRetentionRole
        IpsApiAccount["IpsApiAccount<br/>ApiGateway::Account"]-->IpsApiCloudWatchRole["IpsApiCloudWatchRole<br/>IAM::Role"]
        IpsApiDeployment["IpsApiDeployment<br/>ApiGateway::Deployment"]-->IpsApi["IpsApi<br/>ApiGateway::RestApi"]
        IpsApiStageProd["IpsApiDeploymentStageprod<br/>ApiGateway::Stage"]-->IpsApiDeployment
        IpsApiStageProd-->IpsApi
        IpsApiResource["IpsApiResource<br/>ApiGateway::Resource"]-->IpsApi
        IpsApiPostPermission["IpsApiPostPermission<br/>Lambda::Permission"]-->IpsApi
        IpsApiPostPermission-->IpsApiStageProd
        IpsApiPostPermission-->IpsHandler
        IpsApiPostPermissionTest["IpsApiPostPermissionTest<br/>Lambda::Permission"]-->IpsApi
        IpsApiPostPermissionTest-->IpsHandler
        IpsApiPostMethod["IpsApiPostMethod<br/>ApiGateway::Method"]-->IpsApiResource
        IpsApiPostMethod-->IpsApi
        IpsApiPostMethod-->IpsHandler
        IpsApiKey["IpsApiKey<br/>ApiGateway::ApiKey"]-->IpsApi
        IpsApiKey-->IpsApiStageProd
        IpsApiUsagePlan["IpsApiUsagePlan<br/>ApiGateway::UsagePlan"]-->IpsApi
        IpsApiUsagePlan-->IpsApiStageProd
        IpsApiUsagePlanKey["IpsApiUsagePlanKey<br/>ApiGateway::UsagePlanKey"]-->IpsApiKey
        IpsApiUsagePlanKey-->IpsApiUsagePlan
    end