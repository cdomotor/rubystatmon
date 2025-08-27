/*
 * File: app/javascript/controllers/stopclick_controller.js
 * Path: /app/javascript/controllers/stopclick_controller.js
 * Prevents action buttons from triggering parent link navigation.
 */
import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  stop(e) {
    e.stopPropagation()
  }
}
