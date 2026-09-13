class TrialDataProcessor:
    def process_json(self, json_data):
        """Process the trial JSON and extract relevant fields"""
        basic_info = self._extract_basic_info(json_data)
        therapeutic_context = self._extract_therapeutic_context(json_data)
        intervention_details = self._extract_intervention_details(json_data)
        objectives = self._extract_objectives(json_data)
        study_design = self._extract_study_design(json_data)

        return {
            "basic_info": basic_info,
            "therapeutic_context": therapeutic_context,
            "intervention_details": intervention_details,
            "objectives": objectives,
            "study_design": study_design
        }

    def _extract_basic_info(self, json_data):
        """Extract basic trial information"""
        basic_info = {}

        # Extract title
        if "titleLong" in json_data:
            basic_info["title"] = json_data["titleLong"]

        # Extract phase
        if "phase" in json_data and json_data["phase"] and "name" in json_data["phase"]:
            basic_info["phase"] = json_data["phase"]["name"]

        return basic_info

    def _extract_therapeutic_context(self, json_data):
        """Extract therapeutic context information"""
        therapeutic_context = {}

        # Extract disease area
        if "diseaseArea" in json_data and json_data["diseaseArea"] and "name" in json_data["diseaseArea"]:
            therapeutic_context["disease_area"] = json_data["diseaseArea"]["name"]

        # Extract therapeutic area
        if "therapeuticArea" in json_data and json_data["therapeuticArea"] and "name" in json_data["therapeuticArea"]:
            therapeutic_context["therapeutic_area"] = json_data["therapeuticArea"]["name"]

        return therapeutic_context

    def _extract_intervention_details(self, json_data):
        """Extract intervention details"""
        intervention_details = {}

        # Extract ingredients
        if "interventions" in json_data and json_data["interventions"]:
            ingredients = []
            for intervention in json_data["interventions"]:
                if "ingredients" in intervention and intervention["ingredients"]:
                    for ingredient_item in intervention["ingredients"]:
                        if "ingredient" in ingredient_item and "name" in ingredient_item["ingredient"]:
                            ingredients.append(ingredient_item["ingredient"]["name"])

            if ingredients:
                intervention_details["ingredients"] = ingredients

        # Extract route of administration
        if "routeOfAdministration" in json_data:
            intervention_details["route_of_administration"] = json_data["routeOfAdministration"]

        # Extract intervention groups
        if "interventionGroups" in json_data:
            intervention_details["intervention_groups"] = json_data["interventionGroups"]

        return intervention_details

    def _extract_objectives(self, json_data):
        """Extract study objectives and endpoints"""
        objectives = {}

        # Extract objectives and endpoints
        if "objectivesAndEndpoints" in json_data:
            objectives["objectives_and_endpoints"] = json_data["objectivesAndEndpoints"]

        return objectives

    def _extract_study_design(self, json_data):
        """Extract study design information"""
        study_design = {}

        # Extract study epochs
        if "studyDesign" in json_data and "epochs" in json_data["studyDesign"]:
            study_design["epochs"] = json_data["studyDesign"]["epochs"]

        # Extract inclusion/exclusion criteria
        if "inclusion" in json_data:
            study_design["inclusion_criteria"] = json_data["inclusion"]

        if "exclusion" in json_data:
            study_design["exclusion_criteria"] = json_data["exclusion"]

        return study_design
