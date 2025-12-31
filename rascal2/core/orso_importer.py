def import_ort_project(self, ort_path: str, save_path: str):
    self.model.create_project(Path(ort_path).stem, save_path)

    from rascal2.core.orso_importer import populate_project_from_ort
    populate_project_from_ort(self.model.project, ort_path)

    self.model.results = self.quick_run()
