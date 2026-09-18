package com.aiep;

import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.core.domain.JavaClasses;
import org.junit.jupiter.api.Test;

class ArchitectureTest {
    private final JavaClasses productionClasses = new ClassFileImporter()
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
            .importPackages("com.aiep");

    @Test
    void enforces_platform_and_identity_direction() {
        ArchitectureRules.platformAndIdentityDoNotDependOnBusiness().check(productionClasses);
    }

    @Test
    void prevents_business_modules_from_reading_aggregation_modules() {
        ArchitectureRules.businessLayersDoNotDependOnAggregation().check(productionClasses);
    }

    @Test
    void permits_only_aihub_to_knowledge_l2_dependency() {
        ArchitectureRules.l2DependenciesAreRestricted().check(productionClasses);
    }

    @Test
    void prevents_controller_repository_shortcuts() {
        ArchitectureRules.controllersDoNotAccessRepositories().check(productionClasses);
    }

    @Test
    void prevents_repository_leaks_from_public_apis() {
        ArchitectureRules.apiDoesNotExposeRepositories().check(productionClasses);
    }

    @Test
    void confines_agent_transport_client_to_platform_ai_agent_package() {
        ArchitectureRules.onlyAgentPackageUsesWebClient().check(productionClasses);
    }

    @Test
    void keeps_top_level_packages_free_of_cycles() {
        slices().matching("com.aiep.(*)..").should().beFreeOfCycles().check(productionClasses);
    }
}
