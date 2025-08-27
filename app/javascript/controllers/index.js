/*
 * File: app/javascript/controllers/index.js
 * Path: /app/javascript/controllers/index.js
 */
import { Application } from "@hotwired/stimulus"
import StopclickController from "./stopclick_controller"

window.Stimulus = Application.start()
Stimulus.register("stopclick", StopclickController)
