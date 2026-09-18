package com.aiep;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.lang.CompositeArchRule;

final class ArchitectureRules {
    private static final String[] PLATFORM_AND_IDENTITY = {
            "..platformcore..", "..platformcontent..", "..platformai..", "..platformfile..",
            "..platformtask..", "..identity.."
    };
    private static final String[] BUSINESS_AND_AGGREGATION = {
            "..knowledge..", "..asset..", "..aihub..", "..system..", "..workspace..", "..analytics.."
    };

    private ArchitectureRules() {
    }

    static ArchRule platformAndIdentityDoNotDependOnBusiness() {
        return noClasses().that().resideInAnyPackage(PLATFORM_AND_IDENTITY)
                .should().dependOnClassesThat().resideInAnyPackage(BUSINESS_AND_AGGREGATION)
                .as("platform and identity packages must not depend on business or aggregation packages");
    }

    static ArchRule businessLayersDoNotDependOnAggregation() {
        return noClasses().that().resideInAnyPackage(
                        "..knowledge..", "..asset..", "..aihub..", "..system..")
                .should().dependOnClassesThat().resideInAnyPackage("..workspace..", "..analytics..")
                .as("L2 business packages must not depend on L3 aggregation packages");
    }

    static ArchRule l2DependenciesAreRestricted() {
        ArchRule knowledgeAssetSystemAreIsolated = noClasses()
                .that().resideInAnyPackage("..knowledge..", "..asset..", "..system..")
                .should().dependOnClassesThat().resideInAnyPackage(
                        "..knowledge..", "..asset..", "..aihub..", "..system..")
                .as("knowledge, asset, and system must not depend on another L2 business package");
        ArchRule aihubOnlyDependsOnKnowledgeAtL2 = noClasses().that().resideInAnyPackage("..aihub..")
                .should().dependOnClassesThat().resideInAnyPackage("..asset..", "..system..")
                .as("aihub may only depend on knowledge among L2 business packages");
        return CompositeArchRule.of(knowledgeAssetSystemAreIsolated).and(aihubOnlyDependsOnKnowledgeAtL2);
    }

    static ArchRule controllersDoNotAccessRepositories() {
        return noClasses().that().resideInAnyPackage("..controller..")
                .should().dependOnClassesThat().resideInAnyPackage("..repository..")
                .allowEmptyShould(true)
                .as("controllers must enter domain services instead of repositories");
    }

    static ArchRule apiDoesNotExposeRepositories() {
        return noClasses().that().resideInAnyPackage("..api..")
                .should().dependOnClassesThat().resideInAnyPackage("..repository..")
                .as("public APIs must not expose repository types");
    }

    static ArchRule onlyAgentPackageUsesWebClient() {
        return noClasses().that().resideOutsideOfPackage("..platformai.agent..")
                .should().dependOnClassesThat()
                .haveFullyQualifiedName("org.springframework.web.reactive.function.client.WebClient")
                .as("only com.aiep.platformai.agent may use WebClient for Agent transport");
    }
}
